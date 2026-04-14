#!/usr/bin/env python3
import json
import os
import sys

RESULTS_FILE = 'results.json'
FANOUTS      = [2, 4]


def load():
    if os.path.exists(RESULTS_FILE):
        with open(RESULTS_FILE) as f:
            return json.load(f)
    return {}


def save(data):
    with open(RESULTS_FILE, 'w') as f:
        json.dump(data, f, indent=2)


def add_result(mode, fanout, values):
    data = load()
    runs = data.setdefault(mode, {}).setdefault(str(fanout), [])
    run_id = len(runs) + 1
    entry  = {'run': run_id, 'per_host': values, 'total': sum(values)}
    runs.append(entry)
    save(data)
    print(f'Saved: {mode} N={fanout} run {run_id}')
    print(f'  per host: {values}')
    print(f'  total:    {sum(values):.1f} Mbits/sec')
    print(f'  -> {RESULTS_FILE}')


def print_summary():
    data = load()
    if not data:
        print('No results yet.')
        return
    import statistics
    print('\n=== Results Summary ===')
    for mode in ['ecmp', 'conga']:
        if mode not in data:
            continue
        print(f'\n{mode.upper()}:')
        for fanout, runs in sorted(data[mode].items(), key=lambda x: int(x[0])):
            totals = [r['total'] for r in runs]
            print(f'  N={fanout}: {len(runs)} run(s) | '
                  f'median={statistics.median(totals):.1f} | '
                  f'min={min(totals):.1f} | max={max(totals):.1f} Mbits/sec')
            for r in runs:
                per = '  '.join(f'{v:.1f}' for v in r['per_host'])
                print(f'    run {r["run"]}: [{per}]  total={r["total"]:.1f}')


def plot():
    try:
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        sys.exit('[!] Run: pip install matplotlib numpy')

    data = load()
    if not data:
        sys.exit('[!] No results found. Run some experiments first.')

    fanouts = FANOUTS
    modes   = ['ecmp', 'conga']
    labels  = {'ecmp': 'ECMP', 'conga': 'CONGA-Flow'}
    colors  = {'ecmp': '#9fbdd8', 'conga': '#2c6fad'}
    x       = np.arange(len(fanouts))
    width   = 0.35

    fig, ax = plt.subplots(figsize=(8, 5))

    for idx, mode in enumerate(modes):
        if mode not in data:
            print(f'[!] No data for {mode}, skipping')
            continue
        medians, errors = [], []
        for n in fanouts:
            runs   = data[mode].get(str(n), [])
            totals = [r['total'] for r in runs] if runs else [0]
            medians.append(float(np.median(totals)))
            errors.append(float(np.std(totals)) if len(totals) > 1 else 0)

        ax.bar(x + (idx - 0.5) * width, medians, width,
               yerr=errors, capsize=4,
               label=labels[mode], color=colors[mode],
               edgecolor='white', error_kw={'elinewidth': 1.5})

    ax.set_xlabel('Fanout (number of simultaneous senders)', fontsize=11)
    ax.set_ylabel('Aggregate throughput (Mbits/sec)',        fontsize=11)
    ax.set_title(
        'Incast throughput: ECMP vs CONGA-Flow\n'
        'BMv2/Mininet replication of Figure 13 — Alizadeh et al., SIGCOMM 2014',
        fontsize=10)
    ax.set_xticks(x)
    ax.set_xticklabels([f'N={n}' for n in fanouts])
    ax.legend()
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.grid(axis='y', linestyle='--', alpha=0.4)
    ax.set_ylim(bottom=0)
    plt.tight_layout()

    outfile = 'figure13_replication.png'
    plt.savefig(outfile, dpi=150)
    print(f'\n[*] Plot saved to {outfile}')
    plt.show()


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == 'plot':
        plot()
        return

    if cmd == 'summary':
        print_summary()
        return

    if cmd in ('ecmp', 'conga'):
        if len(sys.argv) < 4:
            print(f'Usage: python3 save_result.py {cmd} <fanout> <h1> [h2] [h3] [h4]')
            sys.exit(1)
        mode   = cmd
        fanout = int(sys.argv[2])
        values = [float(v) for v in sys.argv[3:]]
        if len(values) != fanout:
            print(f'[!] Expected {fanout} bandwidth values, got {len(values)}')
            sys.exit(1)
        add_result(mode, fanout, values)
        print_summary()
        return

    print(f'Unknown command: {cmd}')
    print(__doc__)
    sys.exit(1)


if __name__ == '__main__':
    main()
