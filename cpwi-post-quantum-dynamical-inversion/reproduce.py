
#!/usr/bin/env python3
"""Reproduce the computational checks and small-instance experiments
for the CPWI manuscript.

This script:
  1. computes the illustrative parameter table;
  2. verifies the formal-word recurrence;
  3. checks the relabelling-collapse bijection exhaustively;
  4. implements the CPWI forward map;
  5. measures collisions on small exhaustive instances;
  6. measures brute-force inversion cost;
  7. measures an avalanche/diffusion statistic;
  8. records simple permutation invariants of CPWI outputs.

IMPORTANT:
These experiments are finite-size diagnostics only. They do not prove
classical or post-quantum security.

Python 3.10+; standard library only.
"""
from __future__ import annotations

import csv
import math
import random
import statistics
import time
from collections import Counter
from pathlib import Path
from typing import Callable, Iterable, Sequence, Tuple

Permutation = Tuple[int, ...]
CPWIInstance = tuple[
    Permutation,
    Permutation,
    tuple[tuple[Permutation, Permutation], ...],
    tuple[tuple[Permutation, Permutation], ...],
]


# ---------------------------------------------------------------------------
# Permutation utilities
# ---------------------------------------------------------------------------

def compose(p: Permutation, q: Permutation) -> Permutation:
    """Return p o q (apply q first, then p)."""
    if len(p) != len(q):
        raise ValueError("Permutation degrees differ")
    return tuple(p[q[i]] for i in range(len(p)))


def identity(m: int) -> Permutation:
    """Identity permutation of degree m."""
    return tuple(range(m))


def inversion_parity(p: Sequence[int]) -> int:
    """Return 0 for even permutations and 1 for odd permutations."""
    parity = 0
    for i in range(len(p)):
        for j in range(i + 1, len(p)):
            parity ^= int(p[i] > p[j])
    return parity


def random_even_permutation(m: int, rng: random.Random) -> Permutation:
    """Sample an even permutation by parity-correcting a random permutation."""
    if m < 2:
        raise ValueError("m must be >= 2")
    values = list(range(m))
    rng.shuffle(values)
    if inversion_parity(values):
        values[0], values[1] = values[1], values[0]
    result = tuple(values)
    if inversion_parity(result) != 0:
        raise AssertionError("Parity correction failed")
    return result


def bits_from_int(value: int, n: int) -> Tuple[int, ...]:
    """Encode value as n bits, least-significant bit first."""
    if value < 0:
        raise ValueError("value must be non-negative")
    return tuple((value >> i) & 1 for i in range(n))


def hamming_distance_perm(p: Permutation, q: Permutation) -> int:
    """Number of positions whose images differ."""
    if len(p) != len(q):
        raise ValueError("Permutation degrees differ")
    return sum(a != b for a, b in zip(p, q))


def cycle_lengths(p: Permutation) -> tuple[int, ...]:
    """Return the sorted cycle lengths, including fixed points."""
    seen = [False] * len(p)
    lengths = []
    for start in range(len(p)):
        if seen[start]:
            continue
        cur = start
        length = 0
        while not seen[cur]:
            seen[cur] = True
            cur = p[cur]
            length += 1
        lengths.append(length)
    return tuple(sorted(lengths))


def permutation_order(p: Permutation) -> int:
    """Return the order of a permutation."""
    result = 1
    for length in cycle_lengths(p):
        result = math.lcm(result, length)
    return result


def fixed_points(p: Permutation) -> int:
    """Return the number of fixed points."""
    return sum(i == image for i, image in enumerate(p))


# ---------------------------------------------------------------------------
# Relabelling-collapse theorem check
# ---------------------------------------------------------------------------

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


def verify_relabelling_collapse(
    seed: int = 20260828,
    n: int = 10,
    m: int = 8,
) -> dict:
    rng = random.Random(seed)
    g0 = random_even_permutation(m, rng)
    branches = [
        (random_even_permutation(m, rng), random_even_permutation(m, rng))
        for _ in range(n)
    ]

    salts = [rng.randrange(1, 1 << 30) for _ in range(n)]

    def make_selector(round_index: int, salt: int) -> Callable[[Permutation], int]:
        def selector(g: Permutation) -> int:
            acc = salt ^ (round_index * 0x9E3779B1)
            for j, image in enumerate(g):
                acc = (
                    (acc << 5)
                    ^ (acc >> 2)
                    ^ ((j + 1) * (image + 3))
                ) & 0xFFFFFFFF
            return acc & 1
        return selector

    selectors = [make_selector(i, salts[i]) for i in range(n)]
    seen_branch_sequences = set()

    for value in range(1 << n):
        x = bits_from_int(value, n)
        endpoint, b = relabelled_walk(x, g0, branches, selectors)
        ordinary_endpoint = ordinary_walk(b, g0, branches)
        if endpoint != ordinary_endpoint:
            raise AssertionError("Endpoint mismatch: theorem check failed")
        seen_branch_sequences.add(b)

    expected = 1 << n
    if len(seen_branch_sequences) != expected:
        raise AssertionError("x -> b was not bijective")

    return {
        "seed": seed,
        "n": n,
        "m": m,
        "inputs_checked": expected,
        "distinct_branch_sequences": len(seen_branch_sequences),
        "bijection_verified": True,
        "endpoint_identity_verified": True,
    }


# ---------------------------------------------------------------------------
# CPWI construction
# ---------------------------------------------------------------------------

def generate_cpwi_instance(n: int, m: int, seed: int) -> CPWIInstance:
    """Generate one reproducible public CPWI instance."""
    if n < 1:
        raise ValueError("n must be >= 1")
    if m < 5:
        raise ValueError("m must be >= 5 so A_m is non-abelian simple")

    rng = random.Random(seed)
    u0 = random_even_permutation(m, rng)
    v0 = random_even_permutation(m, rng)

    a = tuple(
        (
            random_even_permutation(m, rng),
            random_even_permutation(m, rng),
        )
        for _ in range(n)
    )
    b = tuple(
        (
            random_even_permutation(m, rng),
            random_even_permutation(m, rng),
        )
        for _ in range(n)
    )

    return u0, v0, a, b


def cpwi_forward(
    x: Sequence[int],
    instance: CPWIInstance,
) -> tuple[Permutation, Permutation]:
    """Evaluate CPWI.

    Recurrence:
        U_i = U_{i-1} A_{i,x_i} V_{i-1} U_{i-1}
        V_i = V_{i-1} B_{i,x_i} U_{i-1} V_{i-1}

    Products are interpreted using compose(p, q) = p o q.
    Both updates use the same previous state (U_{i-1}, V_{i-1}).
    """
    u, v, a, b = instance

    if len(x) != len(a) or len(a) != len(b):
        raise ValueError("Input length and instance round count differ")
    if any(bit not in (0, 1) for bit in x):
        raise ValueError("x must contain only 0/1 bits")

    for i, bit in enumerate(x):
        old_u, old_v = u, v

        # U_i = old_u o A[i][bit] o old_v o old_u
        u = compose(
            old_u,
            compose(
                a[i][bit],
                compose(old_v, old_u),
            ),
        )

        # V_i = old_v o B[i][bit] o old_u o old_v
        v = compose(
            old_v,
            compose(
                b[i][bit],
                compose(old_u, old_v),
            ),
        )

    return u, v


def verify_cpwi_forward(seed: int = 20260908, n: int = 8, m: int = 8) -> dict:
    """Basic deterministic and parity sanity checks."""
    instance = generate_cpwi_instance(n, m, seed)
    x = bits_from_int((1 << n) // 3, n)

    y1 = cpwi_forward(x, instance)
    y2 = cpwi_forward(x, instance)

    if y1 != y2:
        raise AssertionError("CPWI evaluation is not deterministic")
    if inversion_parity(y1[0]) or inversion_parity(y1[1]):
        raise AssertionError("CPWI left A_m")

    return {
        "seed": seed,
        "n": n,
        "m": m,
        "deterministic": True,
        "output_in_Am_squared": True,
    }


# ---------------------------------------------------------------------------
# Illustrative parameter arithmetic
# ---------------------------------------------------------------------------

def minimal_alternating_degree(input_bits: int, margin_bits: int) -> Tuple[int, float]:
    target = input_bits + margin_bits
    m = 5
    while True:
        # |A_m| = m!/2, hence |A_m x A_m| = (m!/2)^2.
        entropy = 2.0 * (math.lgamma(m + 1) / math.log(2.0) - 1.0)
        if entropy >= target:
            return m, entropy
        m += 1


def parameter_rows(margin_bits: int = 16) -> list[dict]:
    """Illustrative sizing based only on generic amplitude amplification."""
    rows = []
    for security_target in (128, 192, 256):
        n = 2 * security_target
        m, output_entropy = minimal_alternating_degree(n, margin_bits)

        # Naive image-list representation: m images, ceil(log2 m) bits each.
        bits_per_permutation = m * math.ceil(math.log2(m))

        # Public data: U0,V0 plus 2 choices for each A_i and B_i:
        # 2 + 4n permutations.
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
                "elementary_image_operations_upper_bound": 6 * n * m,
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Formal-word recurrence
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Small-instance experiments
# ---------------------------------------------------------------------------

def collision_experiment(
    n_values: Sequence[int] = (4, 6, 8, 10, 12, 14),
    m_values: Sequence[int] = (5, 6, 8),
    seeds: Sequence[int] = (101, 202, 303),
) -> list[dict]:
    """Enumerate all inputs and measure endpoint collisions."""
    rows = []

    for m in m_values:
        for n in n_values:
            for seed in seeds:
                instance = generate_cpwi_instance(n, m, seed)
                counts: Counter[tuple[Permutation, Permutation]] = Counter()

                start = time.perf_counter()
                for value in range(1 << n):
                    x = bits_from_int(value, n)
                    counts[cpwi_forward(x, instance)] += 1
                elapsed = time.perf_counter() - start

                inputs = 1 << n
                distinct = len(counts)
                collision_excess = inputs - distinct
                colliding_pairs = sum(c * (c - 1) // 2 for c in counts.values())
                max_preimages = max(counts.values(), default=0)

                rows.append(
                    {
                        "n": n,
                        "m": m,
                        "seed": seed,
                        "inputs": inputs,
                        "distinct_outputs": distinct,
                        "collision_excess": collision_excess,
                        "colliding_pairs": colliding_pairs,
                        "max_preimages": max_preimages,
                        "elapsed_seconds": round(elapsed, 9),
                    }
                )

    return rows


def brute_force_invert(
    target: tuple[Permutation, Permutation],
    instance: CPWIInstance,
    n: int,
) -> tuple[Tuple[int, ...] | None, int]:
    """Return the first preimage found and number of forward evaluations."""
    evaluations = 0
    for value in range(1 << n):
        candidate = bits_from_int(value, n)
        evaluations += 1
        if cpwi_forward(candidate, instance) == target:
            return candidate, evaluations
    return None, evaluations


def inversion_experiment(
    n_values: Sequence[int] = (8, 10, 12, 14, 16),
    m: int = 8,
    seeds: Sequence[int] = (401, 402, 403),
) -> list[dict]:
    """Measure exhaustive inversion cost on reproducible targets."""
    rows = []

    for n in n_values:
        for seed in seeds:
            instance = generate_cpwi_instance(n, m, seed)
            rng = random.Random(seed ^ 0xC0FFEE)
            secret_value = rng.randrange(1 << n)
            secret = bits_from_int(secret_value, n)
            target = cpwi_forward(secret, instance)

            start = time.perf_counter()
            recovered, evaluations = brute_force_invert(target, instance, n)
            elapsed = time.perf_counter() - start

            success = recovered is not None and cpwi_forward(recovered, instance) == target

            rows.append(
                {
                    "n": n,
                    "m": m,
                    "seed": seed,
                    "secret_value_lsb_encoding": secret_value,
                    "evaluations": evaluations,
                    "fraction_of_space_scanned": round(evaluations / (1 << n), 9),
                    "elapsed_seconds": round(elapsed, 9),
                    "target_preimage_found": bool(success),
                    "recovered_original_secret": recovered == secret,
                }
            )

    return rows


def avalanche_experiment(
    n_values: Sequence[int] = (8, 12, 16, 20),
    m_values: Sequence[int] = (6, 8, 10),
    seeds: Sequence[int] = (501, 502, 503),
    samples_per_instance: int = 32,
) -> list[dict]:
    """Measure normalized endpoint change after flipping one input bit."""
    rows = []

    for m in m_values:
        for n in n_values:
            for seed in seeds:
                instance = generate_cpwi_instance(n, m, seed)
                rng = random.Random(seed ^ 0xA11A)

                distances = []
                for _ in range(samples_per_instance):
                    x_value = rng.randrange(1 << n)
                    x = list(bits_from_int(x_value, n))
                    base_u, base_v = cpwi_forward(x, instance)

                    bit_index = rng.randrange(n)
                    x[bit_index] ^= 1
                    flip_u, flip_v = cpwi_forward(x, instance)

                    d = (
                        hamming_distance_perm(base_u, flip_u)
                        + hamming_distance_perm(base_v, flip_v)
                    ) / (2.0 * m)
                    distances.append(d)

                rows.append(
                    {
                        "n": n,
                        "m": m,
                        "seed": seed,
                        "samples": len(distances),
                        "mean_normalized_endpoint_distance": round(
                            statistics.fmean(distances), 9
                        ),
                        "stdev_normalized_endpoint_distance": round(
                            statistics.pstdev(distances), 9
                        ),
                        "min_normalized_endpoint_distance": round(min(distances), 9),
                        "max_normalized_endpoint_distance": round(max(distances), 9),
                    }
                )

    return rows


def structural_invariant_experiment(
    n_values: Sequence[int] = (8, 12, 16),
    m_values: Sequence[int] = (6, 8, 10),
    seeds: Sequence[int] = (601, 602, 603),
    samples_per_instance: int = 64,
) -> list[dict]:
    """Record simple output invariants for exploratory cryptanalysis.

    This does not claim that these invariants are independent of the input.
    It creates machine-readable data for later statistical analysis.
    """
    rows = []

    for m in m_values:
        for n in n_values:
            for seed in seeds:
                instance = generate_cpwi_instance(n, m, seed)
                rng = random.Random(seed ^ 0x51A7)

                for sample in range(samples_per_instance):
                    x_value = rng.randrange(1 << n)
                    x = bits_from_int(x_value, n)
                    u, v = cpwi_forward(x, instance)
                    uv = compose(u, v)

                    rows.append(
                        {
                            "n": n,
                            "m": m,
                            "seed": seed,
                            "sample": sample,
                            "input_hamming_weight": sum(x),
                            "u_fixed_points": fixed_points(u),
                            "v_fixed_points": fixed_points(v),
                            "uv_fixed_points": fixed_points(uv),
                            "u_order": permutation_order(u),
                            "v_order": permutation_order(v),
                            "uv_order": permutation_order(uv),
                            "u_cycle_type": "-".join(map(str, cycle_lengths(u))),
                            "v_cycle_type": "-".join(map(str, cycle_lengths(v))),
                            "uv_cycle_type": "-".join(map(str, cycle_lengths(uv))),
                        }
                    )

    return rows


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

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
    results_dir = out_dir / "results"
    results_dir.mkdir(exist_ok=True)

    params = parameter_rows()
    words = verify_word_recurrence()
    collapse = verify_relabelling_collapse()
    cpwi_check = verify_cpwi_forward()

    collisions = collision_experiment()
    inversions = inversion_experiment()
    avalanche = avalanche_experiment()
    invariants = structural_invariant_experiment()

    write_csv(results_dir / "parameter_table.csv", params)
    write_csv(results_dir / "word_recurrence.csv", words)
    write_csv(results_dir / "collision_experiment.csv", collisions)
    write_csv(results_dir / "inversion_experiment.csv", inversions)
    write_csv(results_dir / "avalanche_experiment.csv", avalanche)
    write_csv(results_dir / "structural_invariants.csv", invariants)

    report_lines = [
        "CPWI reproducibility and finite-instance experiment report",
        "==========================================================",
        "",
        "IMPORTANT:",
        "These finite-size experiments do not prove classical or post-quantum security.",
        "",
        "Relabelling-collapse finite check:",
    ]
    report_lines.extend(f"  {key}: {value}" for key, value in collapse.items())

    report_lines.extend(
        [
            "",
            "CPWI forward-map sanity check:",
        ]
    )
    report_lines.extend(f"  {key}: {value}" for key, value in cpwi_check.items())

    report_lines.extend(
        [
            "",
            f"Parameter rows written: {len(params)}",
            f"Word-recurrence rows written: {len(words)}",
            f"Collision experiment rows written: {len(collisions)}",
            f"Inversion experiment rows written: {len(inversions)}",
            f"Avalanche experiment rows written: {len(avalanche)}",
            f"Structural-invariant rows written: {len(invariants)}",
            "",
            "Output directory:",
            f"  {results_dir}",
        ]
    )

    report = "\n".join(report_lines) + "\n"
    (results_dir / "verification_report.txt").write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
