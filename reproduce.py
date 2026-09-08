#!/usr/bin/env python3
"""Reproduce arithmetic and finite-instance checks for the CPWI manuscript.

This script performs no security experiment. It:
  1. computes the illustrative parameter table;
  2. verifies the formal-word recurrence;
  3. checks the relabelling-collapse bijection exhaustively on small random instances.

Python 3.10+; standard library only.
"""
from __future__ import annotations

import csv
import itertools
import math
import random
from pathlib import Path
from typing import Callable, Iterable, Sequence, Tuple

Permutation = Tuple[int, ...]


def compose(p: Permutation, q: Permutation) -> Permutation:
    """Return p o q (apply q first, then p)."""
    if len(p) != len(q):
        raise ValueError("Permutation degrees differ")
    return tuple(p[q[i]] for i in range(len(p)))


def identity(m: int) -> Permutation:
    return tuple(range(m))


def inversion_parity(p: Sequence[int]) -> int:
    parity = 0
    for i in range(len(p)):
        for j in range(i + 1, len(p)):
            parity ^= int(p[i] > p[j])
    return parity


def random_even_permutation(m: int, rng: random.Random) -> Permutation:
    values = list(range(m))
    rng.shuffle(values)
    if inversion_parity(values):
        values[0], values[1] = values[1], values[0]
    return tuple(values)


def bits_from_int(value: int, n: int) -> Tuple[int, ...]:
    return tuple((value >> i) & 1 for i in range(n))


def relabelled_walk(
    x: Sequence[int],
    g0: Permutation,
    branches: Sequence[Tuple[Permutation, Permutation]],
    selectors: Sequence[Callable[[Permutation], int]],
) -> Tuple[Permutation, Tuple[int, ...]]:
    g = g0
    b_out = []
    for i, bit in enumerate(x):
        b = bit ^ selectors[i](g)
        b_out.append(b)
        g = compose(g, branches[i][b])
    return g, tuple(b_out)


def ordinary_walk(
    b: Sequence[int],
    g0: Permutation,
    branches: Sequence[Tuple[Permutation, Permutation]],
) -> Permutation:
    g = g0
    for i, bit in enumerate(b):
        g = compose(g, branches[i][bit])
    return g


def verify_relabelling_collapse(seed: int = 20260828, n: int = 10, m: int = 8) -> dict:
    rng = random.Random(seed)
    g0 = random_even_permutation(m, rng)
    branches = [
        (random_even_permutation(m, rng), random_even_permutation(m, rng))
        for _ in range(n)
    ]

    salts = [rng.randrange(1, 1 << 30) for _ in range(n)]

    def make_selector(round_index: int, salt: int) -> Callable[[Permutation], int]:
        def selector(g: Permutation) -> int:
            # A deterministic public predicate of the complete state.
            acc = salt ^ (round_index * 0x9E3779B1)
            for j, image in enumerate(g):
                acc = ((acc << 5) ^ (acc >> 2) ^ ((j + 1) * (image + 3))) & 0xFFFFFFFF
            return acc & 1
        return selector

    selectors = [make_selector(i, salts[i]) for i in range(n)]
    seen_branch_sequences = set()
    checked = 0

    for value in range(1 << n):
        x = bits_from_int(value, n)
        endpoint, b = relabelled_walk(x, g0, branches, selectors)
        ordinary_endpoint = ordinary_walk(b, g0, branches)
        if endpoint != ordinary_endpoint:
            raise AssertionError("Endpoint mismatch: theorem check failed")
        seen_branch_sequences.add(b)
        checked += 1

    expected = 1 << n
    if len(seen_branch_sequences) != expected:
        raise AssertionError("x -> b was not bijective")

    return {
        "seed": seed,
        "n": n,
        "m": m,
        "inputs_checked": checked,
        "distinct_branch_sequences": len(seen_branch_sequences),
        "bijection_verified": True,
        "endpoint_identity_verified": True,
    }


def minimal_alternating_degree(input_bits: int, margin_bits: int) -> Tuple[int, float]:
    target = input_bits + margin_bits
    m = 5
    while True:
        entropy = 2.0 * (math.lgamma(m + 1) / math.log(2.0) - 1.0)
        if entropy >= target:
            return m, entropy
        m += 1


def parameter_rows(margin_bits: int = 16) -> list[dict]:
    rows = []
    for security_target in (128, 192, 256):
        n = 2 * security_target
        m, output_entropy = minimal_alternating_degree(n, margin_bits)
        bits_per_permutation = m * math.ceil(math.log2(m))
        public_bits = (4 * n + 2) * bits_per_permutation
        rows.append(
            {
                "generic_quantum_target_bits": security_target,
                "input_bits_n": n,
                "collision_margin_bits_s": margin_bits,
                "alternating_group_degree_m": m,
                "log2_output_space": round(output_entropy, 6),
                "public_description_kib": round(public_bits / 8 / 1024, 6),
                "naive_output_bits": 2 * bits_per_permutation,
                "elementary_image_operations": 6 * n * m,
            }
        )
    return rows


def verify_word_recurrence(rounds: int = 12) -> list[dict]:
    rows = []
    length = 1
    for i in range(rounds + 1):
        closed_form = (3 ** (i + 1) - 1) // 2
        if length != closed_form:
            raise AssertionError(f"Word recurrence mismatch at round {i}")
        rows.append(
            {
                "round": i,
                "recurrence_length": length,
                "closed_form_length": closed_form,
            }
        )
        length = 3 * length + 1
    return rows


def write_csv(path: Path, rows: Iterable[dict]) -> None:
    rows = list(rows)
    if not rows:
        raise ValueError("No rows to write")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    out_dir = Path(__file__).resolve().parent
    params = parameter_rows()
    words = verify_word_recurrence()
    collapse = verify_relabelling_collapse()

    write_csv(out_dir / "parameter_table.csv", params)
    write_csv(out_dir / "word_recurrence.csv", words)

    report_lines = [
        "CPWI manuscript reproducibility report",
        "======================================",
        "",
        "Relabelling-collapse finite check:",
    ]
    report_lines.extend(f"  {key}: {value}" for key, value in collapse.items())
    report_lines.append("")
    report_lines.append("Illustrative parameter table:")
    for row in params:
        report_lines.append("  " + ", ".join(f"{k}={v}" for k, v in row.items()))
    report_lines.append("")
    report_lines.append("Formal-word recurrence verified through round 12.")

    report = "\n".join(report_lines) + "\n"
    (out_dir / "verification_report.txt").write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
