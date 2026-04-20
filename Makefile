BUILD_DIR  = build
PCAP_DIR   = pcaps
LOG_DIR    = logs
RUN_SCRIPT = /home/p4/tutorials/utils/run_exercise.py

all: run

# ── ECMP baseline ────────────────────────────────────────────
run: build-ecmp
	sudo PATH=$(PATH) ${P4_EXTRA_SUDO_OPTS} python3 $(RUN_SCRIPT) \
		-t topology.json \
		-j $(BUILD_DIR)/ecmp.json \
		-b simple_switch_grpc

# ── CONGA-Flow ───────────────────────────────────────────────
run-conga: build-conga
	sudo PATH=$(PATH) ${P4_EXTRA_SUDO_OPTS} python3 $(RUN_SCRIPT) \
		-t topology-conga.json \
		-j $(BUILD_DIR)/conga.json \
		-b simple_switch_grpc

# ── Build targets ────────────────────────────────────────────
build-ecmp: dirs
	p4c-bm2-ss --p4v 16 \
		--p4runtime-files $(BUILD_DIR)/ecmp.p4.p4info.txtpb \
		-o $(BUILD_DIR)/ecmp.json \
		ecmp.p4

build-conga: dirs
	p4c-bm2-ss --p4v 16 \
		--p4runtime-files $(BUILD_DIR)/conga.p4.p4info.txtpb \
		-o $(BUILD_DIR)/conga.json \
		conga.p4

build: build-ecmp build-conga

dirs:
	mkdir -p $(BUILD_DIR) $(PCAP_DIR) $(LOG_DIR)

# ── Cleanup ──────────────────────────────────────────────────
stop:
	sudo PATH=$(PATH) `which mn` -c

clean: stop
	rm -f *.pcap
	rm -rf $(BUILD_DIR) $(LOG_DIR)
