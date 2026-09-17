# CPWI: inverting coupled permutation-word recurrences over alternating groups

Research software accompanying the manuscript **Inverting coupled permutation-word recurrences over alternating groups** by Gautier-Edouard Filardo (Efrei Research Lab). Earlier tags of this repository accompanied the draft *State-dependent dynamical inversion: structural limits and finite-instance tests*.

**Status: exploratory cryptanalysis of an unproven candidate, not a security-certified primitive.** There is no KEM, encryption scheme, signature scheme, trapdoor or validated security parameter set. Every bound in the manuscript is an upper bound on the cost of a particular attack; the code here demonstrates those attacks on small instances and establishes neither security nor insecurity at the degrees once proposed.

## The object

Two registers `U, V` hold even permutations of degree `m`. Round `i` reads input bit `x_i`, selects public constants `A[i][x_i]`, `B[i][x_i]` and updates both registers from the *same* previous state:

```text
U_i = U_{i-1} A_{i,x_i} V_{i-1} U_{i-1}
V_i = V_{i-1} B_{i,x_i} U_{i-1} V_{i-1}
```

Permutations are tuples of images, `compose(p, q)(j) = p(q(j))`, integer inputs are read least-significant bit first. Seeded instance generation is for repeatable experiments, not cryptographic key generation.

## Requirements and execution

Python 3.10 or later. `reproduce.py`, `analyse_results.py`, `make_tables.py` and `round_attack.py` use only the standard library. `run_extension.py` additionally needs `z3-solver==4.13.3.0` (`requirements-extension.txt`).

```bash
python3 reproduce.py                                  # the six original datasets -> results/
python3 analyse_results.py --rerun-dir results        # independent audit -> audit/
python3 make_tables.py                                # six LaTeX tables -> audit/latex_tables/
python3 round_attack.py                               # round solver and backward inversion -> round_results/
pip install -r requirements-extension.txt
python3 run_extension.py                              # Z3 on the exact encoding -> extension_results/
```

None of these commands overwrites an archived file at the repository root. `round_attack.py --quick` and `run_extension.py --smoke` run reduced grids in about a minute. Elapsed times are local observations and differ across machines; every non-timing value is regenerated exactly.

## What is implemented

| File | Content | Manuscript section |
|---|---|---|
| `reproduce.py` | Forward map, parameter arithmetic, formal-word recurrence, relabelling check, exhaustive collisions, sequential-scan inversion, one-bit distances, invariant records | 2, 3, 8.2, 8.3, 8.6 |
| `analyse_results.py` | Independent direct-index evaluator, weighted prefix-state collision accounting, independent-output and layered-random-map comparators, layered state-merging inversion, final-bit distance identity, correlation/randomisation screen | 4, 6, 8.2, 8.3, 8.6 |
| `round_attack.py` | Single-round system `U' = UAVU, V' = VBUV`; constraint-propagation round solver; round-map image density and preimage statistics; backward branching; solver cost curve and its fit; end-to-end backward inversion; elimination-lemma checks; revised parameter rows | 5, 8.4 |
| `smt_attack.py`, `run_extension.py` | Exact `QF_BV` encoding of the inversion problem, Z3 driver with a matched depth-first baseline, 195 encoding tests | 7, 8.5 |
| `make_tables.py` | LaTeX export of the audit tables | — |

### Backward round solving (`round_attack.py`)

Because the full terminal state is published and each round consumes one bit, inverting `n` rounds is exactly `n` sequential instances of the single-round system plus a branch decision. `round_attack.py` measures what that costs:

- **R1** round-map image density and preimage counts, exhaustive over `A_m x A_m` at `m = 5, 6`;
- **R2 / R2b** preimages under the producing and the other branch, and backward children of a uniformly random state (`m = 5`);
- **R3** cost of the constraint-propagation solver in search nodes at `m = 6..13`, five systems per degree, with a least-squares fit of `log2(nodes)` against `m` over `m >= 8` and its extrapolation to `m = 36, 48, 59, 67`;
- **R9** end-to-end inversion of complete instances at `(m, n) = (7, 8), (9, 8), (9, 10), (11, 8)` by backward depth-first search;
- solver cross-check against exhaustive enumeration on 30 systems at `m = 5`, forward re-verification of every solution, and the elimination identity `V = A^-1 U^-1 U' U^-1` on every solution.

The backward search always requests the *complete* solution set of every round system: a reachable state can have five or more preimages under the producing branch, and a truncated enumeration can drop the true predecessor. Outputs: `round_results/*.csv`, `round_results/round_summary.json`, `round_results/latex_tables/`, `round_results/revised_parameter_table.csv`.

### Archived data

The six original CSVs at the repository root (`parameter_table.csv`, `word_recurrence.csv`, `collision_experiment.csv`, `inversion_experiment.csv`, `avalanche_experiment.csv`, `structural_invariants.csv`) and `verification_report.txt` are the datasets of the first draft; their hashes are in `audit/source_manifest.sha256` and they are never modified. `parameter_table.csv` records the *original* sizing rule (`n = 2λ`, smallest `m` with `2 log2|A_m| >= n + 16`, giving `m = 36, 48, 59`); the revised rows produced by `round_attack.py` live in `round_results/revised_parameter_table.csv` and depend on the extrapolated solver cost curve.

## Findings and their limits

- **Forward, small degree.** Retaining one witness per reachable state inverts any target in at most `2 * sum(min(2**i, (m!/2)**2) for i in range(n))` round transitions; the nine `m = 5` targets, including three at `n = 32`, were inverted with about `1.2e5` transitions. This is polynomial in `n` for fixed `m` and vacuous once `(m!/2)**2` exceeds `2**n`.
- **Backward, any degree.** Inverting `n` rounds is `n` single-round systems. The round map is not injective (image density `0.62`–`0.68` at `m = 5, 6`, against `1 - 1/e = 0.632` for a random map), the other branch is solvable in roughly two thirds of cases, and a random state has about two backward children, so backward search is a tree of branching factor two and a meet-in-the-middle attack costs about `2**(n/2)` round-solver calls. The exponential formal-word length plays no role in any of this, and `n` and `m` are two separate security parameters.
- **Round solver.** The constraint-propagation solver costs roughly two bits of search per unit of degree on `m = 6..13` (exact fit in `round_results/round_summary.json`). Extrapolated — an assumption about one algorithm, not a bound — the combined attack costs about `2**190` at the originally proposed `(n, m) = (256, 36)`: below the `2**256` of exhaustive search, above the `2**128` target. The original parameters are not broken by this code; their entire margin is the factor `2**(n/2)`, which is the necessary minimum.
- **Collisions.** At `n = 14, m = 6`, 6,260 unordered colliding pairs were observed across three seeds against 3,106.70 for independent outputs and 6,210.70 for the layered random-map comparator: a shared state inherits its collisions into every common continuation.
- **Distances.** The endpoint distance under a last-bit flip depends only on the last round's constants; the reference distance between independent uniform pairs is `1 - 1/m`, not `1/2`.
- **SMT.** Z3 on the exact encoding solved 37 of 54 planted targets within budget; a matched depth-first search solved all 54 in less time.
- **Invariant screen.** Largest absolute correlation 0.3296; maximum-statistic randomisation comparison 0.713. Linear dependence on Hamming weight only.

Labels such as 128/192/256 in `parameter_table.csv` refer to `n/2` in a generic search calculation and are **not established security levels**. Algebraic attacks on the single-unknown round equation, Gröbner-basis methods, and alternative solver strategies are untried.

## Provenance

`audit/source_manifest.sha256` and `audit/environment_and_provenance.json` identify the archived source files and the audit environment. `round_results/round_summary.json` records the interpreter, platform and SHA-256 of `round_attack.py` and `reproduce.py` for the round experiments. Timings are local; raw measurements are preserved rather than replaced.

## Repository layout

```text
CITATION.cff  LICENSE  README.md  requirements.txt  requirements-extension.txt
reproduce.py  analyse_results.py  make_tables.py  round_attack.py  smt_attack.py  run_extension.py
[the six original CSVs]  verification_report.txt
audit/              independent audit of the archived data (analyse_results.py)
round_results/      round solver, backward inversion, cost fit, revised parameter rows (round_attack.py)
extension_results/  Z3 instances, records and witnesses (run_extension.py; shipped as a release asset)
```

The LaTeX source of the manuscript is distributed as a separate companion archive. Publication of this code does not mean that the manuscript has been peer reviewed or accepted. Code is under `LICENSE` (MIT). Generative AI tools assisted with code development and text drafting; all numerical values come from the archived programs and their recorded outputs, and the author reviewed the mathematics, the sources and the interpretation.
