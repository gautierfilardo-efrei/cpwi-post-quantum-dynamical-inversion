#!/usr/bin/env python3
"""Export the six manuscript LaTeX tables from the archived CPWI audit.

Python >= 3.10, standard library only. Run analyse_results.py first.
Default output: audit/latex_tables/. No original file is overwritten.
"""
from __future__ import annotations
import argparse
import csv
from pathlib import Path


def read_csv(root: Path, name: str) -> list[dict[str, str]]:
    with (root / name).open(newline='', encoding='utf-8') as handle:
        return list(csv.DictReader(handle))


def table(columns: str, header: str, rows: list[list]) -> str:
    # Ragged-right cells avoid stretched words in narrow table headings.
    columns = columns.replace('X', r'>{\raggedright\arraybackslash}X')
    columns = columns.replace('p{', r'>{\raggedright\arraybackslash}p{')
    return ('\\begin{tabularx}{\\textwidth}{@{}' + columns + '@{}}\n\\toprule\n'
            + header + ' \\\\\n\\midrule\n'
            + '\n'.join(' & '.join(map(str, row)) + ' \\\\' for row in rows)
            + '\n\\bottomrule\n\\end{tabularx}\n')


def main() -> None:
    base = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=base)
    parser.add_argument('--output-dir', type=Path, default=base/'audit'/'latex_tables')
    args = parser.parse_args()
    root, output = args.data_dir.resolve(), args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)

    def put(name: str, content: str) -> None:
        (output/name).write_text(content, encoding='utf-8')

    rows = []
    for r in read_csv(root, 'audit/collision_summary.csv'):
        if int(r['n']) == 14:
            rows.append([r['m'], f"{int(r['observed_pairs_total']):,}",
                         f"{float(r['independent_random_expectation_total']):,.2f}",
                         f"{float(r['layered_random_expectation_total']):,.2f}",
                         f"{float(r['ratio_to_independent_random']):.3f}",
                         f"{float(r['ratio_to_layered_random']):.3f}"])
    put('collisions.tex', table('lXXXXX', r'$m$ & Observed pairs & Independent-map expectation & Layered-map expectation & Ratio to independent & Ratio to layered', rows))

    rows = [[r['m'], r['comparisons'], f"{float(r['mean_distance']):.6f}",
             f"{float(r['population_stdev']):.6f}",
             f"{float(r['independent_uniform_reference']):.6f}"]
            for r in read_csv(root, 'audit/avalanche_summary.csv')]
    put('avalanche.tex', table('lXXXX', r'$m$ & Comparisons & Mean $D$ & Descriptive SD & Uniform reference $1-1/m$', rows))

    inv = read_csv(root, 'inversion_experiment.csv')
    rows = []
    for n in (8, 10, 12, 14, 16):
        rr = sorted((r for r in inv if int(r['n']) == n), key=lambda r: int(r['seed']))
        if len(rr) != 3:
            raise ValueError(f'Expected three original inversion rows for n={n}')
        successes = sum(r['target_preimage_found'].lower() == 'true' for r in rr)
        rows.append([n, *[f"{int(r['evaluations']):,}" for r in rr], f'{successes}/{len(rr)}'])
    put('inversion.tex', table('lXXXX', r'$n$ & Seed 401 & Seed 402 & Seed 403 & Valid preimages', rows))

    dp = read_csv(root, 'audit/state_merging_inversion.csv')
    rows = []
    for n in (16, 24, 32):
        rr = [r for r in dp if int(r['n']) == n]
        if len(rr) != 3:
            raise ValueError(f'Expected three state-merging rows for n={n}')
        lo = min(int(r['transition_evaluations']) for r in rr)
        hi = max(int(r['transition_evaluations']) for r in rr)
        peak = max(int(r['peak_frontier_states']) for r in rr)
        successes = sum(r['target_preimage_verified'].lower() == 'true' for r in rr)
        rows.append([n, f'{1<<n:,}', f'{lo:,}--{hi:,}', f'{peak:,}', f'{successes}/{len(rr)}'])
    put('merging.tex', table('lXXXX', r'$n$ & Input strings $2^n$ & Transition evaluations & Largest frontier & Valid preimages', rows))

    rows = [[r['generic_quantum_target_bits'], r['input_bits_n'], r['alternating_group_degree_m'],
             f"{float(r['log2_output_space']):.3f}", f"{float(r['public_description_kib']):.3f}",
             r['naive_output_bits']] for r in read_csv(root, 'parameter_table.csv')]
    put('parameters.tex', table('llXXXX', r'$n/2$ & $n$ & $m$ & $\log_2 M$ & Public data (KiB) & Output storage (bits)', rows))

    # Inventory is the fixed experimental protocol, not a fitted data summary.
    protocol = [
        ['Collisions', r'$n=4,6,8,10,12,14$; $m=5,6,8$', '101, 202, 303', '54 exhaustive instances'],
        ['Sequential inversion', r'$n=8,10,12,14,16$; $m=8$', '401, 402, 403', '15 targets'],
        ['One-bit distances', r'$n=8,12,16,20$; $m=6,8,10$', '501, 502, 503', '36 instances; 32 draws each'],
        ['Invariants', r'$n=8,12,16$; $m=6,8,10$', '601, 602, 603', '27 instances; 64 draws each'],
        ['State-merging inversion', r'$n=16,24,32$; $m=5$', '701, 702, 703', '9 additional targets'],
    ]
    put('protocol.tex', table('p{3.0cm}Xp{2.7cm}p{3.1cm}', r'Experiment & Parameters & Seeds & Recorded units', protocol))
    print(f'Six manuscript tables written to {output}')


if __name__ == '__main__':
    main()
