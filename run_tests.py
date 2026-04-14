#!/usr/bin/env python3

import json
import os
import time

#config
RESULTS_FILE = '/home/p4/tutorials/exercises/conga-replication/results.json'
RECV_IP      = '10.0.5.5'
IPERF_DUR    = 10
WAIT_AFTER   = 15
FANOUTS      = [2, 4]
N_RUNS       = 5

#mode is set by the user before running this script
try:
    MODE = AUTOEXP_MODE
except NameError:
    MODE = 'ecmp'

def save_result(mode, fanout, values):
    if os.path.exists(RESULTS_FILE):
        with open(RESULTS_FILE) as f:
            data = json.load(f)
    else:
        data = {}
    runs = data.setdefault(mode, {}).setdefault(str(fanout), [])
    run_id = len(runs) + 1
    runs.append({'run': run_id, 'per_host': values, 'total': sum(values)})
    with open(RESULTS_FILE, 'w') as f:
        json.dump(data, f, indent=2)
    return run_id


def run_one(net, n_senders, run_id):
    hrecv   = net.get('hrecv')
    senders = [net.get(f'h{i+1}') for i in range(n_senders)]

    #kill any leftover iperf
    hrecv.cmd('pkill -f iperf 2>/dev/null; sleep 0.2')

    #start server
    hrecv.cmd('iperf -s -D')
    time.sleep(1.0)

    #start all clients simultaneously
    for h in senders:
        h.cmd(f'iperf -c {RECV_IP} -t {IPERF_DUR} '
              f'> /tmp/iperf_{h.name}.txt 2>&1 &')

    #wait for flows to finish
    print(f'  [run {run_id}/{N_RUNS}] waiting {WAIT_AFTER}s...', flush=True)
    time.sleep(WAIT_AFTER)

    #parse results
    values = []
    for h in senders:
        out  = h.cmd(f'cat /tmp/iperf_{h.name}.txt')
        mbps = 0.0
        for line in out.split('\n'):
            if 'Mbits/sec' in line:
                try:
                    mbps = float(line.strip().split()[-2])
                except (ValueError, IndexError):
                    pass
        values.append(mbps)
        print(f'    {h.name}: {mbps:.1f} Mbits/sec')

    total = sum(values)
    print(f'    TOTAL: {total:.1f} Mbits/sec')

    #kill server
    hrecv.cmd('pkill -f iperf 2>/dev/null')
    time.sleep(1)

    return values


def print_summary():
    if not os.path.exists(RESULTS_FILE):
        print('No results yet.')
        return
    with open(RESULTS_FILE) as f:
        data = json.load(f)

    print('\n=== Results Summary ===')
    for mode in ['ecmp', 'conga']:
        if mode not in data:
            continue
        print(f'\n{mode.upper()}:')
        for fanout, runs in sorted(data[mode].items(), key=lambda x: int(x[0])):
            totals = [r['total'] for r in runs]
            import statistics
            med = statistics.median(totals)
            print(f'  N={fanout}: {len(runs)} runs | '
                  f'median={med:.1f} | '
                  f'min={min(totals):.1f} | '
                  f'max={max(totals):.1f} Mbits/sec')
            for r in runs:
                per = '  '.join(f'{v:.1f}' for v in r['per_host'])
                print(f'    run {r["run"]}: [{per}]  total={r["total"]:.1f}')



print(f'\n{"="*50}')
print(f'AUTOEXP: mode={MODE}, fanouts={FANOUTS}, runs={N_RUNS}')
print(f'{"="*50}')

for fanout in FANOUTS:
    print(f'\n--- Fanout N={fanout} ---')
    for run_id in range(1, N_RUNS + 1):
        values = run_one(net, fanout, run_id)
        saved_id = save_result(MODE, fanout, values)
        print(f'  -> saved run {saved_id} to results.json')
        time.sleep(2)

print('\n[*] All experiments complete.')
print_summary()
