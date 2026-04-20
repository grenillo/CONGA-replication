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

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5))
    fig.suptitle(
        'ECMP vs CONGA-Flow: Incast Throughput\n'
        'BMv2/Mininet replication — Alizadeh et al., SIGCOMM 2014',
        fontsize=11)

    # ── Left panel: aggregate throughput (median ± std across runs) ───────────
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

        ax1.bar(x + (idx - 0.5) * width, medians, width,
                yerr=errors, capsize=4,
                label=labels[mode], color=colors[mode],
                edgecolor='white', error_kw={'elinewidth': 1.5})

    ax1.set_xlabel('Fanout (number of simultaneous senders)', fontsize=11)
    ax1.set_ylabel('Aggregate throughput (Mbits/sec)', fontsize=11)
    ax1.set_title('Aggregate Throughput\n(median ± std across runs)', fontsize=10)
    ax1.set_xticks(x)
    ax1.set_xticklabels([f'N={n}' for n in fanouts])
    ax1.legend()
    ax1.spines['top'].set_visible(False)
    ax1.spines['right'].set_visible(False)
    ax1.grid(axis='y', linestyle='--', alpha=0.4)
    ax1.set_ylim(bottom=0)

    # ── Right panel: per-host throughput std dev (fairness metric) ────────────
    # Computed as average within-run std dev across all runs for each condition.
    # Lower = more even distribution across senders within a single experiment.
    for idx, mode in enumerate(modes):
        if mode not in data:
            continue
        within_run_stds = []
        for n in fanouts:
            runs = data[mode].get(str(n), [])
            if not runs:
                within_run_stds.append(0)
                continue
            per_run_stds = [float(np.std(r['per_host'])) for r in runs]
            within_run_stds.append(float(np.mean(per_run_stds)))

        ax2.bar(x + (idx - 0.5) * width, within_run_stds, width,
                label=labels[mode], color=colors[mode], edgecolor='white')

    ax2.set_xlabel('Fanout (number of simultaneous senders)', fontsize=11)
    ax2.set_ylabel('Avg within-run std dev (Mbits/sec)', fontsize=11)
    ax2.set_title('Per-Host Throughput Fairness\n(lower = more even distribution)', fontsize=10)
    ax2.set_xticks(x)
    ax2.set_xticklabels([f'N={n}' for n in fanouts])
    ax2.legend()
    ax2.spines['top'].set_visible(False)
    ax2.spines['right'].set_visible(False)
    ax2.grid(axis='y', linestyle='--', alpha=0.4)
    ax2.set_ylim(bottom=0)

    plt.tight_layout()

    outfile = 'figure13_replication.png'
    plt.savefig(outfile, dpi=150, bbox_inches='tight')
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
