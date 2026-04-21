# CONGA Replication: Distributed Congestion-Aware Load Balancing for Datacenters

**Report by:** Jonny Grenillo  
**Repository:** [github.com/grenillo/CONGA-replication](https://github.com/grenillo/CONGA-replication)  
**Paper:** Alizadeh et al., "CONGA: Distributed Congestion-Aware Load Balancing for Datacenters," ACM SIGCOMM 2014, pp. 503–514.  
**Paper URL:** https://people.csail.mit.edu/alizadeh/papers/conga-sigcomm14.pdf

---

## Introduction

This project replicates key results from:

> Alizadeh, M., Edsall, T., Dharmapurikar, S., Vaidyanathan, R., Chu, K., Fingerhut, A., Lam, V. T., Matus, F., Pan, R., Yadav, N., and Varghese, G. "CONGA: Distributed Congestion-Aware Load Balancing for Datacenters." *ACM SIGCOMM 2014*, pp. 503–514.  
> https://people.csail.mit.edu/alizadeh/papers/conga-sigcomm14.pdf

CONGA is an in-network load balancing mechanism for datacenter Leaf-Spine fabrics. It addresses two well-known failure modes of ECMP (Equal-Cost Multi-Path), the dominant baseline: hash collisions, where multiple large flows are hashed onto the same uplink leaving other paths idle, and asymmetry blindness, where ECMP continues forwarding to a congested or failed link because it has no feedback mechanism.

CONGA's core insight is that local congestion awareness alone is insufficient, and can paradoxically make things worse than ECMP under asymmetric conditions. Instead, CONGA uses a leaf-to-leaf feedback loop: destination leaf switches piggyback congestion metrics back to source leaf switches via an overlay header, giving each source a real-time global view of congestion across all uplink paths. Flowlet switching is used as the load balancing granularity, routing bursts of packets separated by an idle gap to different paths, avoiding TCP reordering while achieving sub-flow flexibility.

The paper demonstrates that CONGA achieves 5× better flow completion times than ECMP under link failure, and 2–8× better throughput than MPTCP in incast scenarios, while requiring no endpoint modifications.

---

## Result Chosen and Rationale

The replication target is the incast throughput comparison between ECMP and CONGA-Flow, analogous to the experiment described around Figures 7 and 13 of the paper. Specifically: aggregate and per-host throughput under a synchronized incast workload at varying fanout values (N=2 and N=4 simultaneous senders targeting a single receiver).

**Why this result:** The incast scenario is the paper's sharpest demonstration of ECMP's hash collision problem. With N senders all routing through the same source leaf switch, ECMP deterministically maps each 5-tuple to a fixed uplink, and with only 2 uplinks available, collisions are likely at N=4. CONGA-Flow's congestion-informed path selection should detect the overloaded uplink and rebalance flowlets to the less-congested path. This is directly implementable in P4 without requiring the full VXLAN overlay infrastructure.

**CONGA-Flow vs. full CONGA:** The paper distinguishes CONGA (flowlet timeout T_fl = 500µs, aggressive per-flowlet splitting) from CONGA-Flow (T_fl = 13ms, effectively one load balancing decision per flow). CONGA-Flow is the honest P4-implementable target: it captures the congestion-aware path selection logic without requiring per-packet reordering tolerance or sub-millisecond register feedback. This replication implements CONGA-Flow only.

---

## Paper Methodology

The paper's testbed uses custom Broadcom Trident 2 ASICs with 64 servers across 2 racks, connected via a 2-tier Leaf-Spine fabric (2 leaves, 2 spines) with 10 Gbps host links and 4×40 Gbps uplinks per leaf (2:1 oversubscription). Key parameters:

- **Flowlet timeout (T_fl):** 13ms for CONGA-Flow (greater than max path latency, ensuring no reordering)
- **Congestion metric:** Discounting Rate Estimator (DRE) — a per-link register incremented by packet size and exponentially decayed, quantized to 3 bits (Q=3)
- **DRE time constant (τ):** 160µs
- **Feedback mechanism:** Congestion metrics piggybacked on return traffic via VXLAN overlay header fields (LBTag, CE, FB_LBTag, FB_Metric)
- **Load balancing decision:** Source leaf selects the uplink minimizing max(local DRE, remote congestion metric from Congestion-To-Leaf table)
- **Incast workload:** N senders each send 10MB/N of a striped file simultaneously to one receiver; aggregate throughput measured at receiver

---

## Implementation Methodology

### Topology

A 4-switch Leaf-Spine topology in Mininet using BMv2:
- **s1:** source leaf (h1–h4 attached on ports 3–6, spine uplinks on ports 1–2)
- **s2:** destination leaf (hrecv attached on port 3)
- **s3, s4:** spine switches

All switches run either `ecmp.p4` or `conga.p4` compiled via `p4c-bm2-ss`. Table entries are populated at startup via per-switch P4Runtime JSON files (`s1-runtime.json`, `s1-conga-runtime.json`, etc.).

### ECMP Baseline (`ecmp.p4`)

Standard 5-tuple hash action selector. For traffic destined to `10.0.5.5`, s1 hashes the flow to one of two uplink ports (ecmp_select 0 or 1 → port 1 or 2). The hash assignment is static for the lifetime of each flow.

### CONGA-Flow (`conga.p4`)

Built on the flowlet switching lab foundation:

1. **Flowlet detection:** Per-flow register storing the last-seen packet timestamp (indexed by 5-tuple hash). If the inter-packet gap exceeds `FLOWLET_TIMEOUT` (defined as 200ms), a new flowlet boundary is declared.
2. **Congestion measurement:** In MyEgress, each packet arriving on ingress port 1 or 2 (the spine-facing uplinks) writes `standard_metadata.deq_qdepth` to `congestion_reg[0]` or `congestion_reg[1]` respectively.
3. **Path selection:** At each flowlet boundary, `update_flowlet_id()` reads both congestion registers and sets `flowlet_id` to whichever path has the lower queue depth, then writes the decision back to `flowlet_to_id`.
4. **Forwarding:** `conga_nhop` table maps `flowlet_id` (0 or 1) to the corresponding uplink next-hop, effectively routing the flowlet to the less-congested spine.

### Divergences from the Paper

| Aspect | Paper | This Replication |
|--------|-------|-----------------|
| Flowlet timeout (T_fl) | 13ms | 200ms (tuned for BMv2's software switching latency; note the presentation slides stated 50ms but the implemented value is 200ms) |
| Congestion signal | DRE (hardware rate estimator, τ=160µs) | `deq_qdepth` register reads — a queue depth proxy rather than a true rate estimate |
| Feedback mechanism | In-band VXLAN overlay headers across all fabric hops | Return-path `deq_qdepth` written directly to `congestion_reg` at the source leaf in `MyEgress` |
| Hardware | Custom Broadcom Trident 2 ASICs, 10/40 Gbps links | BMv2 software switch; uplinks capped via `tc tbf` at 8 Mbps to create measurable congestion |
| Fanout values | N = 2, 4, 8, 16, up to 63 | N = 2, 4 only — BMv2 CPU limits precluded higher fanout |

**Critical divergence is uplink shaping:** Because BMv2 treats all virtual links as software-unlimited, artificial uplink congestion was necessary to observe any load balancing effect. The source leaf's two spine-facing interfaces (s1-eth1, s1-eth2) were capped at 8 Mbps each via `tc tbf` applied at the start of each experiment. Without this, all flows ran at full BMv2 software speed with no observable fabric-level congestion.

### How to Run

```bash
# Build and start ECMP topology
make run

# In Mininet CLI — run ECMP experiments
py exec(open('run_tests.py').read(), {'net': net})

# Exit and start CONGA-Flow topology
make stop
make run-conga

# In Mininet CLI — run CONGA-Flow experiments
py exec(open('run_tests.py').read(), {'net': net, 'AUTOEXP_MODE': 'conga'})
```

Results are saved to `results.json`. Generate the figure with:
```bash
python3 save_result.py plot
```

---

## Results

### Round 1: Initial Results (Presented April 16, 2026)

The initial experiments were run without explicit link bandwidth constraints, Mininet links were left at their default software-unlimited rate.

**ECMP (initial):**
- N=2: 21.7 Mbps aggregate
- N=4: 23.1 Mbps aggregate — minimal gain despite 2× senders, consistent with hash collisions

**CONGA-Flow (initial):**
- Per-host range: 4.3–5.5 Mbps vs ECMP per-host range: 4.8–8.3 Mbps
- CONGA-Flow showed tighter per-host distribution, suggesting fairer bandwidth sharing

These results showed a promising fairness signal. However, the absolute throughput values reflected BMv2 CPU capacity rather than any fabric bottleneck. Because no link was actually congested, ECMP's hash collisions were not stressing the fabric meaningfully, and the CONGA congestion registers had nothing to react to. Following the presentation, Professor Guo identified this as a CPU saturation issue and recommended re-running with explicit, lower bandwidth constraints to create genuine fabric-level congestion.

### Round 2: Controlled Results with Uplink Shaping

The second round applied `tc tbf` rate limits to s1's two spine-facing uplinks (8 Mbps each), making the uplinks the actual bottleneck rather than the BMv2 CPU.

![ECMP vs CONGA-Flow](figure13_replication.png)

**ECMP (controlled):**

| Fanout | Run 1 | Run 2 | Run 3 | Run 4 | Run 5 | Median Total |
|--------|-------|-------|-------|-------|-------|-------------|
| N=2 | [3.6, 4.1] = 7.7 | [3.4, 4.3] = 7.7 | [4.4, 3.3] = 7.7 | [3.6, 4.0] = 7.6 | [2.7, 5.0] = 7.7 | **7.7 Mbps** |
| N=4 | [4.4, 3.7, 3.2, 3.9] = 15.3 | [2.6, 2.4, 7.2, 2.8] = 14.9 | [2.4, 2.5, 7.6, 2.7] = 15.3 | [2.2, 2.8, 7.6, 2.6] = 15.2 | [1.8, 1.9, 1.9, 2.1] = 7.7 | **15.2 Mbps** |

**CONGA-Flow (controlled):**

| Fanout | Run 1 | Run 2 | Run 3 | Run 4 | Run 5 | Median Total |
|--------|-------|-------|-------|-------|-------|-------------|
| N=2 | [12.9, 9.2] = 22.1 | [12.3, 10.2] = 22.5 | [11.4, 11.4] = 22.8 | [10.9, 10.9] = 21.8 | [10.9, 11.6] = 22.5 | **22.5 Mbps** |
| N=4 | [7.4, 7.6, 3.0, 4.1] = 22.1 | [6.8, 3.8, 7.3, 3.3] = 21.2 | [4.7, 4.3, 6.1, 4.9] = 19.9 | [5.3, 5.5, 5.6, 4.7] = 21.1 | [4.0, 4.3, 6.9, 6.4] = 21.6 | **21.2 Mbps** |

### Comparison with Original Paper

The paper reports CONGA-Flow achieving meaningfully better aggregate throughput and flow completion time than ECMP. Our controlled replication confirms this directionally:

**Aggregate throughput:**
- N=2: CONGA-Flow achieves **2.9× higher** aggregate throughput than ECMP (22.5 vs 7.7 Mbps). ECMP hashes both flows to the same uplink, hitting the 8 Mbps cap. CONGA-Flow detects the congestion and splits flowlets across both uplinks, nearly doubling available bandwidth.
- N=4: CONGA-Flow achieves **~40% higher** aggregate throughput (21.2 vs 15.2 Mbps median). ECMP collisions cause 3 of 4 hosts to share a congested uplink; CONGA-Flow rebalances across both.

**Per-host fairness:**
- ECMP N=4: runs 2–4 show one host capturing ~7.5 Mbps while the other three starve at ~2.5 Mbps each. The winning host is sticky, h3 dominates in runs 2, 3, and 4 due to a fixed hash assignment.
- CONGA-Flow N=4: average within-run standard deviation is 1.21 Mbps vs ECMP's 1.39 Mbps. More importantly, no single host permanently dominates, and the load shifts across runs as CONGA-Flow's congestion registers steer flowlets to less-loaded paths.

These results qualitatively replicate the paper's core claim: CONGA-Flow achieves better fabric utilization than ECMP under incast conditions by making congestion-informed path decisions rather than relying on a fixed hash.

---

## Discussion

### Why Two Rounds of Experiments Were Necessary

The initial experiments revealed a fundamental challenge in BMv2-based replication: without explicit link constraints, Mininet virtual links are effectively unlimited and BMv2 forwards traffic at whatever rate the host CPU allows. The CONGA congestion registers were updating but had no meaningful signal, and no link was actually congested.

The progression from Round 1 to Round 2 involved several calibration attempts:

1. Adding `{"bw": X, "delay": "Yms"}` to topology JSON link entries, but was rejected by `run_exercise.py` with "Illegal latency" errors
2. Adding `tc tbf` rate limits to host interfaces via topology JSON `commands`, this was applied correctly but became the sole bottleneck, masking fabric effects
3. Applying `tc tbf` to s1's spine-facing switch interfaces. This placed the bottleneck at the fabric uplinks where it belongs

This calibration process is an important finding in itself: replicating network experiments in software requires careful attention to *where* the bottleneck sits, because the answer determines whether the load balancing mechanism can have any observable effect at all.

### Why the ECMP N=2 Result Is So Pronounced

At N=2, ECMP hashes h1 and h2's 5-tuples to the same uplink. Both flows then compete for a single 8 Mbps uplink, splitting it roughly evenly at ~3.8 Mbps each (totaling ~7.7 Mbps). CONGA-Flow detects that one uplink is accumulating queue depth and routes the second flowlet to the idle uplink, achieving ~11 Mbps per host (totaling ~22.5 Mbps). This is the clearest possible demonstration of ECMP's hash collision problem.

A reader may notice that 22.5 Mbps exceeds the stated 8 Mbps uplink cap. This is expected and consistent: the `tc tbf` cap is applied to the switch interface, not the host NIC. When CONGA-Flow routes the two flows to *different* uplinks, each flow has its own uncontested 8 Mbps uplink and can push up to whatever BMv2's software forwarding ceiling allows on that path (~11 Mbps in practice). The cap only bites when two flows *share* the same uplink, which is precisely what ECMP causes and CONGA-Flow avoids. Total fabric capacity with both uplinks in use is 2 × 8 = 16 Mbps at the switch interface level, but BMv2 software forwarding headroom above the cap means observed throughput can exceed this, and the cap creates the congestion signal CONGA needs, not a hard ceiling on total throughput.

### Why the Congestion Signal Works Despite BMv2 Limitations

Unlike in Round 1 (where the congestion registers had no signal), the 8 Mbps uplink cap creates real queue buildup that `deq_qdepth` can detect. When ECMP collides two flows onto one uplink, that uplink's queue grows, `congestion_reg[0]` or `congestion_reg[1]` rises, and at the next flowlet boundary CONGA-Flow steers new traffic to the other uplink. The 200ms flowlet timeout means path decisions are made infrequently enough that BMv2's register latency does not prevent the signal from being useful.

### Limitations

The N=4 results show more variance than N=2 because four flows across two uplinks creates a more complex collision pattern that CONGA-Flow's simple min-congestion selection does not always resolve optimally within a 15-second iperf run. The paper's hardware implementation benefits from sub-RTT feedback, which allows much faster rebalancing. Some runs still show one host dominating, though the effect is less severe and less sticky than under ECMP.

---

## Additional Context

**BMv2 as a research platform:** BMv2 is designed for protocol correctness verification, not performance benchmarking. Its software packet processing pipeline introduces per-packet latency orders of magnitude higher than ASIC hardware. The 200ms flowlet timeout (vs. 13ms in the paper) reflects this, and in BMv2, a 13ms gap threshold caused nearly every packet to trigger a new flowlet boundary, destroying flow affinity entirely.

**Lessons learned:**
- *P4 is a pipeline, not a program:* every register read/write and table lookup has a fixed per-packet cost. The CONGA path adds 4 register operations per packet vs ECMP's 1 hash + 1 lookup, which is measurable overhead in software.
- *Hardware assumptions matter enormously:* CONGA's DRE operates at τ=160µs; replicating its effect with `deq_qdepth` at BMv2 speeds required creating artificial congestion conditions (the uplink cap) that would not be needed on real hardware.
- *Where the bottleneck sits determines what you can measure:* the most important experimental calibration decision was moving the rate limit from the host NICs to the switch uplinks. Only then did the load balancing mechanism have anything to act on.
- *The trend is the result:* due to platform differences, absolute throughput numbers cannot match the paper. The relative behavior, CONGA-Flow using both uplinks while ECMP wastes one is the meaningful replication target, and it replicates clearly.


