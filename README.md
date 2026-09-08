# CPWI: finite-instance experiments and structural audit

Research software accompanying the draft **State-dependent dynamical inversion: structural limits and finite-instance tests** by Gautier-Edouard Filardo.

**Status: exploratory research, not a security-certified primitive.** There is no KEM, encryption scheme, signature scheme, trapdoor or validated security parameter set. The audit demonstrates efficient inversion at fixed small permutation degree; it does not establish security or insecurity for all growing-degree families.

## Requirements and execution

Use Python 3.10 or later. All three scripts use only the Python standard library; no package installation or Colab account is required. Open a terminal in the downloaded repository folder and run:

```bash
python3 reproduce.py
python3 analyse_results.py --rerun-dir results
```

The first command regenerates the original six datasets and a verification report into `results/`. It leaves the archived CSV files at the repository root unchanged. The second command independently checks those archived results, compares them with the new `results/` files, and generates the supplementary audit into `audit/`. It overwrites previous audit outputs, not the original root datasets. Execution times and environment records will differ across computers.

The additional audit can also run on its own:

```bash
python3 analyse_results.py
```

It validates the archived deterministic data and runs the new diagnostics without requiring a separate literal rerun. Optional settings are shown by `python3 analyse_results.py --help`.

To regenerate the six LaTeX tables from the audit data, run `python3 make_tables.py`. The files are written to `audit/latex_tables/`; they match the companion Overleaf `tables/` files.

## What is implemented

The original `reproduce.py` is unchanged. It implements both register updates using the same previous state, with rightmost-first permutation composition. Integer input encodings are least-significant-bit first. Seeded instance generation is for repeatable experiments, not cryptographic key generation.

Original archived files:

```text
parameter_table.csv          3 illustrative arithmetic rows
word_recurrence.csv         13 formal recurrence rows
collision_experiment.csv    54 exhaustive finite-instance rows
inversion_experiment.csv    15 sequential-search rows
avalanche_experiment.csv    36 distance-summary rows
structural_invariants.csv 1728 sampled invariant records
verification_report.txt       original execution report
```

The invariant product is `U V`, not `U V^{-1}`. The distance is normalized Hamming distance on permutation images, not binary-bit avalanche.

The new `analyse_results.py` includes a separate direct-index forward evaluator; weighted prefix-state enumeration and collision accounting; an independent-output and a layered-random-map collision comparator; state-merging inversion; final-bit distance identities; and an exploratory correlation/randomisation diagnostic. Full experiment settings and seeds are encoded explicitly in the programs and written to the outputs.

## Findings and their limits

The audit supplied with the manuscript reproduced all six original CSVs outside elapsed-time columns. Independent direct-index checks passed on 834 inputs; collision accounting matched 486 intermediate layers; all 1,152 final-bit identities held. These validate computations, not security assumptions.

For fixed `m`, one can retain one witness per reachable state. An exact inversion algorithm uses at most `2 * sum(min(2**i, (m!/2)**2) for i in range(n))` round transitions. The nine supplied `m=5` targets were all inverted. The three `n=32` runs required 121,272–122,734 transitions, in a state space of only 3,600 elements. These are round transitions, not complete forward evaluations, and are not a break of an established 32-bit security level. Any valid preimage counts as inversion success.

At `n=14,m=6`, 6,260 unordered collision pairs were observed across three seeds. The summed independent-output expectation is 3,106.70; the explicitly defined layered-random-map expectation is 6,210.70. Agreement with one expectation does not establish a random-map distribution.

Final-bit endpoint distance depends exactly on the two selected pairs of last-round constants and is independent of the preceding message. The uniform image-distance reference is `1 - 1/m`, not `1/2`. Large distances are not a proof of cryptographic diffusion or one-wayness.

The invariant screen examines only six numeric features against input weight, separately in 27 blocks. Its largest absolute correlation is about 0.329553; an exploratory maximum-statistic randomisation comparison gives 0.713. This does not rule out nonlinear, categorical or individual-bit leakage.

No SAT/CSP, Groebner-basis, meet-in-the-middle, quantum circuit or hidden-subgroup attack is implemented in these materials. Sequential exhaustive search is a baseline, not evidence that the best attack has exponential complexity. Labels such as 128/192/256 in the original parameter CSV refer only to `n/2` in a generic unique-preimage search calculation; they are **not established CPWI security levels**. The original column named `log2_output_space` measures capacity, not demonstrated output entropy.

## Audit provenance

`audit/source_manifest.sha256` and `audit/environment_and_provenance.json` identify the exact supplied source files and the environment used for this audit. New timings are local observations. The original archived timing rows did not supply enough hardware provenance to attribute them to a particular Mac or CPU. Raw measurements are preserved, not silently replaced by a new machine's times.

The original twelve-file snapshot was shown in a user-provided GitHub screenshot with short commit `824ed95`; this package does not claim independent remote verification of that commit. This revision has no declared release tag or DOI. `CITATION.cff` intentionally omits a release version and release date until an actual release exists.

## Repository layout

```text
CITATION.cff
LICENSE
README.md
requirements.txt
reproduce.py
analyse_results.py
make_tables.py
[the six original CSVs]
verification_report.txt
audit/
    audit_report.txt
    audit_summary.json
    prefix_collision_audit.csv
    collision_summary.csv
    state_merging_inversion.csv
    avalanche_samples.csv
    avalanche_summary.csv
    last_bit_distance.csv
    structural_correlations.csv
    environment_and_provenance.json
    source_manifest.sha256
    latex_tables/
```

The Overleaf source is distributed as a separate companion archive. Publication of this code does not mean that the manuscript has been peer reviewed or accepted. Source-code licensing is specified in `LICENSE`. AI assistance with formulation, software, analysis support and drafting is disclosed in the manuscript; author review and approval remain necessary.
