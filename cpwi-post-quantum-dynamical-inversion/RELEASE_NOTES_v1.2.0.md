# Release notes — v1.2.0

## Added
- `round_attack.py`: standard-library implementation of the single-round system `U' = UAVU, V' = VBUV`, a constraint-propagation round solver, exhaustive round-map statistics (R1), branch statistics (R2, R2b), the solver cost curve with its least-squares fit and extrapolation (R3), end-to-end backward inversion of complete instances (R9), a solver cross-check against exhaustive enumeration, and forward/elimination-lemma verification of every solution.
- `round_results/`: CSV records, `round_summary.json` (with interpreter, platform and source hashes), LaTeX tables, and `revised_parameter_table.csv`.
- README rewritten to cover all six programs; CITATION.cff updated (title, version, keywords).

## Unchanged
- `reproduce.py`, `analyse_results.py`, `make_tables.py`, `smt_attack.py`, `run_extension.py`, the six archived CSVs, `verification_report.txt` and `audit/` are byte-identical to v1.1.0. `audit/source_manifest.sha256` still verifies.

## Notes for the manuscript
- The manuscript (Section 5 and Section 8.4) quotes the values in `round_results/round_summary.json`: fitted slope 1.98 bits per unit of degree, intercept -9.16, extrapolations 2^62.1 / 2^85.8 / 2^107.5 at m = 36 / 48 / 59, combined attack about 2^190 at (n, m) = (256, 36), revised degree m = 70 at the 128-bit level.
- Every seed is derived from a labelled string by SHA-256 (`CPWI-R1-round-map|m|trial`, `CPWI-R2-branch|m|t`, `CPWI-R2b-spurious|m|t`, `CPWI-R3-solver|m|t`, `CPWI-R9-instance|m|n`, `CPWI-R9-input|m|n`, `CPWI-RX-crosscheck|m`).
- After tagging, replace `COMMIT-TO-FILL` in `main.tex` (Supplementary information and Code availability) by the short hash of the tagged commit, and attach `CPWI_Extended_Reproducibility.zip` to the release as before.

## Before publishing
- `challenges/secrets.local.json` belongs to the separate `cpwi` repository and is gitignored there; it is not part of this repository and must not be added.
