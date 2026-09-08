#!/usr/bin/env python3
"""Audit the supplied CPWI dataset and run finite-state diagnostics.

Python >= 3.10; standard library only. The original reproduce.py is unchanged.
This program does not certify classical or post-quantum security.

Run next to reproduce.py and the six original CSV files:
    python3 analyse_results.py

The original CSVs are never overwritten. Audit outputs go into audit/.
A --rerun-dir can point to a separate execution of reproduce.py; timing columns
are deliberately excluded from deterministic comparisons.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import platform
import random
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

CSV_NAMES = (
    'parameter_table.csv', 'word_recurrence.csv', 'collision_experiment.csv',
    'inversion_experiment.csv', 'avalanche_experiment.csv', 'structural_invariants.csv',
)
METRICS = ('u_fixed_points', 'v_fixed_points', 'uv_fixed_points',
           'u_order', 'v_order', 'uv_order')


def read_csv(path: Path) -> list[dict]:
    with path.open(newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise ValueError(f'No records to write to {path}')
    with path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def load_reference(path: Path):
    spec = importlib.util.spec_from_file_location('cpwi_reference', path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'Cannot import {path}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def compare_records(stored: list[dict], regenerated: list[dict], *,
                    ignore: tuple[str, ...] = ()) -> int:
    """Compare every non-ignored cell; tolerate only stored decimal rounding."""
    if len(stored) != len(regenerated):
        raise AssertionError(f'Row count differs: {len(stored)} != {len(regenerated)}')
    cells = 0
    for index, (a, b) in enumerate(zip(stored, regenerated), start=1):
        if set(a) != set(b):
            raise AssertionError(f'Column names differ in row {index}')
        for key in a:
            if key in ignore:
                continue
            x, y = str(a[key]), str(b[key])
            equal = x == y
            if not equal:
                try:
                    equal = math.isclose(float(x), float(y), rel_tol=0.0, abs_tol=1.1e-9)
                except ValueError:
                    pass
            if not equal:
                raise AssertionError(f'Row {index}, {key}: {x!r} != {y!r}')
            cells += 1
    return cells


def step(state: tuple, a: tuple, b: tuple) -> tuple:
    """Independent direct-index evaluator, not a call to compose()."""
    u, v = state
    return (tuple(u[a[v[u[j]]]] for j in range(len(u))),
            tuple(v[b[u[v[j]]]] for j in range(len(v))))


def forward_direct(value: int, instance: tuple) -> tuple:
    u, v, aa, bb = instance
    state = (u, v)
    for i in range(len(aa)):
        bit = (value >> i) & 1
        state = step(state, aa[i][bit], bb[i][bit])
    return state


def weighted_layers(instance: tuple) -> tuple[list[dict], Counter]:
    """Exact reachable-state multiplicities; no sampling of input prefixes."""
    u, v, aa, bb = instance
    counts = Counter({(u, v): 1})
    previous_pairs = 0
    rows = []
    for i, (a, b) in enumerate(zip(aa, bb), start=1):
        nxt = Counter()
        for state, multiplicity in counts.items():
            nxt[step(state, a[0], b[0])] += multiplicity
            nxt[step(state, a[1], b[1])] += multiplicity
        pairs = sum(k * (k-1) // 2 for k in nxt.values())
        inherited = 2 * previous_pairs
        new_pairs = pairs - inherited
        if new_pairs < 0 or sum(nxt.values()) != 1 << i:
            raise AssertionError('Collision conservation identity failed')
        rows.append({
            'round': i, 'inputs': 1 << i, 'distinct_states': len(nxt),
            'collision_pairs': pairs, 'inherited_pairs': inherited,
            'new_pairs': new_pairs, 'max_preimages': max(nxt.values()),
            'transition_evaluations': 2 * len(counts),
        })
        counts, previous_pairs = nxt, pairs
    return rows, counts


def layered_random_expectation(n: int, cardinality: int) -> float:
    """Exact expectation for independent random branch maps at every layer.

    This comparator is NOT an assertion about the CPWI map distribution.
    Pair inputs whose last different bit is n-ell have a common suffix ell.
    """
    log_no_collision = math.log1p(-1.0 / cardinality)
    return sum((1 << (2*n - ell - 2)) *
               (-math.expm1((ell+1)*log_no_collision)) for ell in range(n))


def merging_inversion(target: tuple, instance: tuple) -> dict:
    """One representative prefix per reachable state; deterministic full layers.

    Prefixes are stored as Python integers in the same LSB-first convention.
    The entire final layer is built, so transition counts do not depend on the
    order in which a target happens to be encountered.
    """
    u, v, aa, bb = instance
    representatives = {(u, v): 0}
    total = 0
    peak = 1
    for i, (a, b) in enumerate(zip(aa, bb)):
        nxt = {}
        for state, prefix in representatives.items():
            for bit in (0, 1):
                new_state = step(state, a[bit], b[bit])
                total += 1
                if new_state not in nxt:
                    nxt[new_state] = prefix | (bit << i)
        representatives = nxt
        peak = max(peak, len(nxt))
    recovered = representatives.get(target)
    return {'recovered_value': recovered, 'transition_evaluations': total,
            'peak_frontier_states': peak, 'final_frontier_states': len(representatives)}


def centred(values: list[float]) -> tuple[list[float], float]:
    mean = statistics.fmean(values)
    result = [x-mean for x in values]
    return result, math.sqrt(sum(x*x for x in result))


def correlation(x: list[float], y: list[float], nx: float, ny: float) -> float:
    if nx == 0 or ny == 0:
        return 0.0  # recorded as undefined separately by caller if needed
    return sum(a*b for a, b in zip(x, y)) / (nx*ny)


def structural_screen(records: list[dict], permutations: int) -> tuple[list[dict], dict]:
    groups = defaultdict(list)
    for r in records:
        groups[tuple(int(r[k]) for k in ('n', 'm', 'seed'))].append(r)
    prepared, results = [], []
    for key in sorted(groups):
        rows = groups[key]
        x, nx = centred([float(r['input_hamming_weight']) for r in rows])
        tests = []
        for metric in METRICS:
            y, ny = centred([float(r[metric]) for r in rows])
            r = correlation(x, y, nx, ny)
            idx = len(results)
            results.append(dict(zip(('n', 'm', 'seed'), key), metric=metric,
                                samples=len(rows), pearson_r=r,
                                defined=(nx > 0 and ny > 0)))
            tests.append((idx, y, ny))
        prepared.append((x, nx, tests))
    rng = random.Random(2026090801)
    null_max = []
    exceed = [0] * len(results)
    for _ in range(permutations):
        maximum = 0.0
        for x, nx, tests in prepared:
            shuffled = x.copy()
            rng.shuffle(shuffled)
            for idx, y, ny in tests:
                magnitude = abs(correlation(shuffled, y, nx, ny))
                exceed[idx] += magnitude >= abs(results[idx]['pearson_r']) - 1e-15
                maximum = max(maximum, magnitude)
        null_max.append(maximum)
    for idx, r in enumerate(results):
        magnitude = abs(r['pearson_r'])
        r['permutations'] = permutations
        r['unadjusted_randomisation_p'] = (1 + exceed[idx]) / (permutations + 1)
        r['global_maxT_p'] = (1 + sum(z >= magnitude-1e-15 for z in null_max)) / (permutations+1)
    strongest = max(results, key=lambda r: abs(r['pearson_r']))
    return results, {
        'tests': len(results), 'permutations': permutations,
        'largest_absolute_r': abs(strongest['pearson_r']),
        'strongest_test': strongest,
        'maxT_rejections_at_0_05': sum(r['global_maxT_p'] < 0.05 for r in results),
        'interpretation': 'Exploratory within-instance weight/invariant screen only; not a leakage bound.',
    }


def run(args) -> None:
    base = Path(__file__).resolve().parent
    data = args.data_dir.resolve()
    out = args.output_dir.resolve()
    if not (data/'reproduce.py').exists():
        raise FileNotFoundError(f'reproduce.py not found in {data}')
    out.mkdir(parents=True, exist_ok=True)
    ref = load_reference(data/'reproduce.py')
    original = {name: read_csv(data/name) for name in CSV_NAMES}
    checks = []
    provenance = {
        'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'python': sys.version, 'platform': platform.platform(),
        'processor': platform.processor() or 'not reported by platform.processor()',
        'timing_policy': 'Local illustrative elapsed times only; no hardware-normalised claims.',
        'source': 'User-supplied files, corresponding to screenshot short commit 824ed95; remote identity not verified.',
        'files': {name: hashlib.sha256((data/name).read_bytes()).hexdigest()
                  for name in (*CSV_NAMES, 'reproduce.py', 'verification_report.txt')},
    }
    # Regenerate all deterministic non-collision datasets with the original code.
    print('Checking original arithmetic, forward map, and stored non-timing data...', flush=True)
    for name, rows in (
        ('parameter_table.csv', ref.parameter_rows()),
        ('word_recurrence.csv', ref.verify_word_recurrence()),
        ('inversion_experiment.csv', ref.inversion_experiment()),
        ('avalanche_experiment.csv', ref.avalanche_experiment()),
        ('structural_invariants.csv', ref.structural_invariant_experiment()),
    ):
        cells = compare_records(original[name], rows, ignore=('elapsed_seconds',))
        checks.append({'check': name, 'rows': len(rows), 'cells': cells, 'passed': True})
    collapse = ref.verify_relabelling_collapse()
    compared = 0
    for m in (5, 6, 8):
        for n in (1, 2, 4, 8):
            inst = ref.generate_cpwi_instance(n, m, 20260908 + 100*m + n)
            for value in range(1 << n):
                if forward_direct(value, inst) != ref.cpwi_forward(ref.bits_from_int(value, n), inst):
                    raise AssertionError('Independent forward implementations disagree')
                compared += 1
    # A layered weighted computation checks all terminal collision multiplicities.
    print('Checking all collision rows with an independent weighted-layer computation...', flush=True)
    prefix_rows = []
    for r in original['collision_experiment.csv']:
        n, m, seed = (int(r[k]) for k in ('n', 'm', 'seed'))
        inst = ref.generate_cpwi_instance(n, m, seed)
        layers, counts = weighted_layers(inst)
        regenerated = {'inputs': 1 << n, 'distinct_outputs': len(counts),
                       'collision_excess': (1 << n)-len(counts),
                       'colliding_pairs': layers[-1]['collision_pairs'],
                       'max_preimages': max(counts.values())}
        for key, value in regenerated.items():
            if int(r[key]) != value:
                raise AssertionError(f'Collision mismatch: n={n}, m={m}, seed={seed}, {key}')
        total_new = 0
        for layer in layers:
            weighted = layer['new_pairs'] * (1 << (n-layer['round']))
            total_new += weighted
            prefix_rows.append({'n': n, 'm': m, 'seed': seed, **layer,
                                'new_pairs_weighted_to_terminal': weighted})
        if total_new != int(r['colliding_pairs']):
            raise AssertionError('Terminal collision decomposition failed')
    checks.append({'check': 'collision_experiment.csv', 'rows': 54, 'cells': 54*5, 'passed': True})
    write_csv(out/'prefix_collision_audit.csv', prefix_rows)
    # Table of honest comparators, aggregated across seeds, not fitted models.
    collision_summary = []
    for m in (5, 6, 8):
        M = (math.factorial(m)//2)**2
        for n in (4, 6, 8, 10, 12, 14):
            rr = [r for r in original['collision_experiment.csv'] if int(r['n']) == n and int(r['m']) == m]
            N = 1 << n
            observed = sum(int(r['colliding_pairs']) for r in rr)
            independent = len(rr) * N*(N-1)/(2*M)
            layered = len(rr)*layered_random_expectation(n, M)
            collision_summary.append({
                'n': n, 'm': m, 'instances': len(rr), 'state_space_cardinality': M,
                'observed_pairs_total': observed, 'independent_random_expectation_total': independent,
                'layered_random_expectation_total': layered,
                'ratio_to_independent_random': observed/independent,
                'ratio_to_layered_random': observed/layered,
                'distinct_outputs_min': min(int(r['distinct_outputs']) for r in rr),
                'distinct_outputs_max': max(int(r['distinct_outputs']) for r in rr),
            })
    write_csv(out/'collision_summary.csv', collision_summary)
    # Reconstruct individual avalanche draws, retaining the flipped position.
    avalanche_samples, last_bit_rows = [], []
    for r in original['avalanche_experiment.csv']:
        n, m, seed = (int(r[k]) for k in ('n', 'm', 'seed'))
        inst = ref.generate_cpwi_instance(n, m, seed)
        rng = random.Random(seed ^ 0xA11A)
        for sample in range(int(r['samples'])):
            value = rng.randrange(1 << n)
            j = rng.randrange(n)
            a, b = forward_direct(value, inst), forward_direct(value ^ (1 << j), inst)
            d = sum(x != y for p, q in zip(a, b) for x, y in zip(p, q))/(2*m)
            avalanche_samples.append({'n': n, 'm': m, 'seed': seed, 'sample': sample,
                                      'input_value_lsb': value, 'flipped_bit_1_based': j+1,
                                      'distance': d})
        aa, bb = inst[2], inst[3]
        predicted = (sum(x != y for x, y in zip(aa[-1][0], aa[-1][1])) +
                     sum(x != y for x, y in zip(bb[-1][0], bb[-1][1])))/(2*m)
        tests = []
        for value in range(32):
            a, b = forward_direct(value, inst), forward_direct(value ^ (1 << (n-1)), inst)
            measured = sum(x != y for p, q in zip(a, b) for x, y in zip(p, q))/(2*m)
            if measured != predicted:
                raise AssertionError('Last-bit bi-invariance identity failed')
            tests.append(measured)
        last_bit_rows.append({'n': n, 'm': m, 'seed': seed, 'prefixes_checked': 32,
                              'branch_constant_prediction': predicted,
                              'minimum_distance': min(tests), 'maximum_distance': max(tests),
                              'identity_verified': True})
    write_csv(out/'avalanche_samples.csv', avalanche_samples)
    write_csv(out/'last_bit_distance.csv', last_bit_rows)
    avalanche_summary = []
    for m in (6, 8, 10):
        values = [r['distance'] for r in avalanche_samples if r['m'] == m]
        avalanche_summary.append({'m': m, 'comparisons': len(values),
                                  'mean_distance': statistics.fmean(values),
                                  'population_stdev': statistics.pstdev(values),
                                  'independent_uniform_reference': 1 - 1/m,
                                  'minimum': min(values), 'maximum': max(values)})
    write_csv(out/'avalanche_summary.csv', avalanche_summary)
    # Demonstrate the bounded-state attack at fixed m, not at proposed large m.
    print('Running bounded-state merging inversion (m=5)...', flush=True)
    dp_rows = []
    for n in (16, 24, 32):
        for seed in (701, 702, 703):
            m = 5
            inst = ref.generate_cpwi_instance(n, m, seed)
            digest = hashlib.sha256(f'CPWI/state-merge-target/v1/{n}/{m}/{seed}'.encode('ascii')).digest()
            secret = random.Random(int.from_bytes(digest, 'big')).getrandbits(n)
            target = forward_direct(secret, inst)
            start = time.perf_counter()
            result = merging_inversion(target, inst)
            elapsed = time.perf_counter()-start
            recovered = result['recovered_value']
            verified = recovered is not None and ref.cpwi_forward(ref.bits_from_int(recovered, n), inst) == target
            if not verified:
                raise AssertionError('State-merging inversion returned an invalid preimage')
            dp_rows.append({'n': n, 'm': m, 'seed': seed, 'secret_value_lsb': secret,
                            **result, 'target_preimage_verified': verified,
                            'recovered_original_secret': recovered == secret,
                            'elapsed_seconds': round(elapsed, 9),
                            'state_bound': 3600,
                            'full_input_space': 1 << n})
    write_csv(out/'state_merging_inversion.csv', dp_rows)
    print('Running within-instance invariant/weight randomisation screen...', flush=True)
    correlations, structural_summary = structural_screen(original['structural_invariants.csv'], args.permutations)
    write_csv(out/'structural_correlations.csv', correlations)
    # Optional second, literal execution of original code supplied by the caller.
    literal_rerun = []
    if args.rerun_dir is not None:
        for name in CSV_NAMES:
            rows = read_csv(args.rerun_dir/name)
            literal_rerun.append({'file': name, 'rows': len(rows),
                                 'cells_compared': compare_records(original[name], rows, ignore=('elapsed_seconds',)),
                                 'passed': True})
    summary = {
        'original_checks': checks, 'independent_forward_inputs_checked': compared,
        'relabelling_check': collapse, 'literal_original_rerun': literal_rerun,
        'prefix_audit_rows': len(prefix_rows),
        'collision_summary_at_n14': [r for r in collision_summary if r['n'] == 14],
        'avalanche_summary': avalanche_summary,
        'last_bit_identity_checks': sum(r['prefixes_checked'] for r in last_bit_rows),
        'state_merging_experiments': dp_rows, 'structural_screen': structural_summary,
        'security_status': 'No demonstrated average-case or post-quantum security; fixed-small-state inversion succeeds.',
    }
    (out/'audit_summary.json').write_text(json.dumps(summary, indent=2)+'\n', encoding='utf-8')
    (out/'environment_and_provenance.json').write_text(json.dumps(provenance, indent=2)+'\n', encoding='utf-8')
    (out/'source_manifest.sha256').write_text(''.join(f'{digest}  {name}\n' for name, digest in provenance['files'].items()), encoding='utf-8')
    text = [
        'CPWI AUDIT — deterministic data checks and finite-state limitations',
        '='*68,
        f'Original deterministic dataset checks: {len(checks)}/6 passed.',
        f'Independent direct-index forward evaluations: {compared} passed.',
        f'Weighted prefix audit rows: {len(prefix_rows)}; all terminal counts matched.',
        f'Last-bit distance identities checked: {summary["last_bit_identity_checks"]}.',
        f'State-merging inversions: {len(dp_rows)}/{len(dp_rows)} valid preimages.',
        f'Invariant screen tests: {structural_summary["tests"]}; max |r|={structural_summary["largest_absolute_r"]:.9f}.',
        f'Global randomisation p for strongest test: {structural_summary["strongest_test"]["global_maxT_p"]:.6f}.',
        '', 'No security certification follows from these checks.',
        'A transition evaluation is not a full n-round forward evaluation.',
        'New elapsed times depend on the local execution environment.',
        'Raw archived timings are preserved, not claimed to be Mac timings.',
    ]
    (out/'audit_report.txt').write_text('\n'.join(text)+'\n', encoding='utf-8')
    print('\n'.join(text))
    print(f'\nOutputs: {out}')


def main() -> None:
    base = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=base)
    parser.add_argument('--output-dir', type=Path, default=base/'audit')
    parser.add_argument('--rerun-dir', type=Path, default=None)
    parser.add_argument('--permutations', type=int, default=999)
    args = parser.parse_args()
    if args.permutations < 99:
        parser.error('--permutations must be at least 99')
    try:
        run(args)
    except (OSError, ValueError, AssertionError) as error:
        print(f'AUDIT FAILED: {error}', file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == '__main__':
    main()
