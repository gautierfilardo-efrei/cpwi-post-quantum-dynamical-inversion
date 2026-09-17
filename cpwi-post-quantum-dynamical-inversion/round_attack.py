#!/usr/bin/env python3
"""Backward round solving for CPWI: round-map statistics, a reference
single-round solver, its cost curve, and end-to-end inversion.

The single-round two-register word system is

    U' = U A V U ,      V' = V B U V            (unknowns U, V in A_m)

or, pointwise with (pq)(j) = p(q(j)),

    U'(j) = U(A(V(U(j)))) ,     V'(j) = V(B(U(V(j)))) .

Inverting an n-round CPWI target is exactly n sequential instances of this
system plus a branch decision (manuscript, Theorem "Round reduction").  This
script measures everything the manuscript's Section "Round statistics, a
reference round solver and backward inversion" reports:

  R1  image density and preimage counts of the round map, exhaustive over
      A_m x A_m at m = 5 and m = 6;
  R2  preimage counts under the producing and the other branch map, and the
      fraction of "other branch solvable" cases, at m = 5;
  R2b backward children of a uniformly random state at m = 5;
  R3  cost of the constraint-propagation round solver at m = 6..13 in search
      nodes, five systems per degree, with a least-squares fit of log2(nodes)
      against m over m >= 8 and its extrapolation;
  R9  end-to-end inversion of complete instances by backward depth-first
      search with the round solver;
  RL  the elimination identity V = A^-1 U^-1 U' U^-1 on every solver output.

Python >= 3.10, standard library only.  Permutation conventions are those of
reproduce.py (tuples of images, compose(p, q) = p o q, least-significant bit
first).  Instances and targets are drawn with random.Random from explicit
seeds derived from labelled strings, so every non-timing value is
reproducible; timings are local observations only.

Usage:
    python3 round_attack.py            # full run (several minutes)
    python3 round_attack.py --quick    # reduced grid, about a minute
Outputs go to round_results/ and do not touch any archived file.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import platform
import random
import statistics
import sys
import time
from math import exp, log2
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reproduce import (  # noqa: E402
    Permutation,
    compose,
    cpwi_forward,
    generate_cpwi_instance,
    inversion_parity,
    random_even_permutation,
)

_NA = -1


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def inverse(p: Permutation) -> Permutation:
    out = [0] * len(p)
    for i, img in enumerate(p):
        out[img] = i
    return tuple(out)


def round_map(u: Permutation, v: Permutation, a: Permutation, b: Permutation):
    """One CPWI round (U, V) -> (U A V U, V B U V), same convention as
    cpwi_forward: compose(p, q) = p o q, both updates read the old state."""
    return (compose(u, compose(a, compose(v, u))),
            compose(v, compose(b, compose(u, v))))


def alternating_group(m: int) -> list[Permutation]:
    return [p for p in itertools.permutations(range(m)) if not inversion_parity(p)]


def seed_from(label: str, *args) -> int:
    text = label + "|" + "|".join(str(a) for a in args)
    return int.from_bytes(hashlib.sha256(text.encode()).digest(), "big")


# ---------------------------------------------------------------------------
# The reference round solver: depth-first search with constraint propagation
# ---------------------------------------------------------------------------

def solve_round(up: Permutation, vp: Permutation, a: Permutation, b: Permutation,
                max_solutions: int = 1, node_budget: int = 300_000):
    """Enumerate solutions (U, V) of U' = UAVU, V' = VBUV.

    Returns (solutions, stats).  stats["nodes"] counts search nodes and
    stats["exhausted"] tells whether the node budget stopped the search, in
    which case the returned list is not exhaustive.
    """
    m = len(up)
    ai, bi = inverse(a), inverse(b)
    sols: list[tuple[Permutation, Permutation]] = []
    state = {"nodes": 0, "exhausted": False}

    def assign(arr, arri, pos, val) -> bool:
        if arr[pos] != _NA:
            return arr[pos] == val
        if arri[val] != _NA:
            return False
        arr[pos] = val
        arri[val] = pos
        return True

    def propagate(u, ui, v, vi) -> bool:
        changed = True
        while changed:
            changed = False
            for j in range(m):
                # chain for U'(j) = u[a[v[u[j]]]]
                p = u[j]
                if p != _NA:
                    q = v[p]
                    if q != _NA:
                        r = a[q]
                        if u[r] == _NA:
                            if not assign(u, ui, r, up[j]):
                                return False
                            changed = True
                        elif u[r] != up[j]:
                            return False
                    else:
                        r = ui[up[j]]
                        if r != _NA:
                            if not assign(v, vi, p, ai[r]):
                                return False
                            changed = True
                else:
                    r = ui[up[j]]
                    if r != _NA:
                        p2 = vi[ai[r]]
                        if p2 != _NA:
                            if not assign(u, ui, j, p2):
                                return False
                            changed = True
                # chain for V'(j) = v[b[u[v[j]]]]
                p = v[j]
                if p != _NA:
                    q = u[p]
                    if q != _NA:
                        r = b[q]
                        if v[r] == _NA:
                            if not assign(v, vi, r, vp[j]):
                                return False
                            changed = True
                        elif v[r] != vp[j]:
                            return False
                    else:
                        r = vi[vp[j]]
                        if r != _NA:
                            if not assign(u, ui, p, bi[r]):
                                return False
                            changed = True
                else:
                    r = vi[vp[j]]
                    if r != _NA:
                        p2 = ui[bi[r]]
                        if p2 != _NA:
                            if not assign(v, vi, j, p2):
                                return False
                            changed = True
        return True

    def dfs(u, ui, v, vi) -> None:
        state["nodes"] += 1
        if state["nodes"] > node_budget:
            state["exhausted"] = True
            return
        j = next((k for k in range(m) if u[k] == _NA), None)
        which = "u"
        if j is None:
            j = next((k for k in range(m) if v[k] == _NA), None)
            which = "v"
            if j is None:
                cu, cv = round_map(tuple(u), tuple(v), a, b)
                if cu == up and cv == vp:
                    sols.append((tuple(u), tuple(v)))
                return
        for val in range(m):
            if (ui if which == "u" else vi)[val] != _NA:
                continue
            u2, ui2, v2, vi2 = u[:], ui[:], v[:], vi[:]
            arr, arri = (u2, ui2) if which == "u" else (v2, vi2)
            if assign(arr, arri, j, val) and propagate(u2, ui2, v2, vi2):
                dfs(u2, ui2, v2, vi2)
                if len(sols) >= max_solutions:
                    return
            if state["exhausted"]:
                return

    blank = [_NA] * m
    dfs(blank[:], blank[:], blank[:], blank[:])
    return sols, dict(nodes=state["nodes"], exhausted=state["exhausted"],
                      found=len(sols))


def enumerate_round_preimages(up, vp, a, b, group):
    """Exhaustive preimages of (U', V') under one round; small degree only."""
    return [(u, v) for u in group for v in group if round_map(u, v, a, b) == (up, vp)]


def elimination_holds(u, v, up, a) -> bool:
    """Lemma (Elimination): V = A^-1 U^-1 U' U^-1."""
    ui = inverse(u)
    return v == compose(inverse(a), compose(ui, compose(up, ui)))


# ---------------------------------------------------------------------------
# Backward depth-first inversion (Theorem "Round reduction")
# ---------------------------------------------------------------------------

def invert_backward(instance, target, node_budget: int = 300_000,
                    max_solutions: int = 1, max_expansions: int = 10_000_000):
    """Return (preimages, stats).  At round i both branch values are tried,
    the round system is solved for each, and a path is accepted only if it
    reaches the public (U_0, V_0) after n steps."""
    u0, v0, a, b = instance
    n = len(a)
    found: list[list[int]] = []
    stats = {"expansions": 0, "round_solves": 0, "round_nodes": 0,
             "budget_exhausted_solves": 0, "elimination_checks": 0,
             "elimination_failures": 0}

    def rec(u, v, i, suffix):
        if stats["expansions"] > max_expansions:
            return
        if i < 0:
            if (u, v) == (u0, v0):
                found.append(list(suffix))
            return
        stats["expansions"] += 1
        for bit in (0, 1):
            # Completeness (Theorem "Round reduction") needs the FULL solution
            # set of every round system: a reachable state can have five or
            # more preimages under the producing branch, and truncating the
            # enumeration can drop the true predecessor.
            sols, st = solve_round(u, v, a[i][bit], b[i][bit],
                                   max_solutions=10 ** 6, node_budget=node_budget)
            stats["round_solves"] += 1
            stats["round_nodes"] += st["nodes"]
            stats["budget_exhausted_solves"] += int(st["exhausted"])
            for (uu, vv) in sols:
                stats["elimination_checks"] += 1
                stats["elimination_failures"] += int(
                    not elimination_holds(uu, vv, u, a[i][bit]))
                rec(uu, vv, i - 1, [bit] + suffix)
                if len(found) >= max_solutions:
                    return

    rec(target[0], target[1], n - 1, [])
    return found, stats


# ---------------------------------------------------------------------------
# Experiments
# ---------------------------------------------------------------------------

def r1_round_map_statistics(degrees=(5, 6), maps_per_degree=(6, 2)):
    rows = []
    for m, k in zip(degrees, maps_per_degree):
        group = alternating_group(m)
        domain = len(group) ** 2
        for trial in range(k):
            rng = random.Random(seed_from("CPWI-R1-round-map", m, trial))
            a = random_even_permutation(m, rng)
            b = random_even_permutation(m, rng)
            counts: dict = {}
            for u in group:
                for v in group:
                    key = round_map(u, v, a, b)
                    counts[key] = counts.get(key, 0) + 1
            c = list(counts.values())
            rows.append(dict(m=m, trial=trial, group_order=len(group),
                             domain=domain, image_size=len(c),
                             image_density=len(c) / domain,
                             mean_preimages_reachable=sum(x * x for x in c) / sum(c),
                             max_preimages=max(c)))
        print(f"  [R1] m={m} done", flush=True)
    return rows


def r2_branch_statistics(m=5, trials=120):
    group = alternating_group(m)
    rows = []
    for t in range(trials):
        rng = random.Random(seed_from("CPWI-R2-branch", m, t))
        a0, a1, b0, b1 = [random_even_permutation(m, rng) for _ in range(4)]
        u, v = random_even_permutation(m, rng), random_even_permutation(m, rng)
        bit = rng.randrange(2)
        ab, bb = (a0, b0) if bit == 0 else (a1, b1)
        aw, bw = (a1, b1) if bit == 0 else (a0, b0)
        up, vp = round_map(u, v, ab, bb)
        k_right = len(enumerate_round_preimages(up, vp, ab, bb, group))
        k_wrong = len(enumerate_round_preimages(up, vp, aw, bw, group))
        rows.append(dict(m=m, trial=t, preimages_producing_branch=k_right,
                         preimages_other_branch=k_wrong,
                         other_branch_solvable=int(k_wrong > 0)))
    print("  [R2] done", flush=True)
    return rows


def r2b_spurious_branching(m=5, trials=200):
    group = alternating_group(m)
    rows = []
    for t in range(trials):
        rng = random.Random(seed_from("CPWI-R2b-spurious", m, t))
        a0, a1, b0, b1 = [random_even_permutation(m, rng) for _ in range(4)]
        ur, vr = random_even_permutation(m, rng), random_even_permutation(m, rng)
        k = (len(enumerate_round_preimages(ur, vr, a0, b0, group))
             + len(enumerate_round_preimages(ur, vr, a1, b1, group)))
        rows.append(dict(m=m, trial=t, backward_children=k))
    print("  [R2b] done", flush=True)
    return rows


def r3_solver_scaling(degrees, systems=5, budget=300_000):
    rows = []
    for m in degrees:
        for t in range(systems):
            rng = random.Random(seed_from("CPWI-R3-solver", m, t))
            u, v, a, b = [random_even_permutation(m, rng) for _ in range(4)]
            up, vp = round_map(u, v, a, b)
            t0 = time.perf_counter()
            sols, st = solve_round(up, vp, a, b, max_solutions=1, node_budget=budget)
            dt = time.perf_counter() - t0
            elim = all(elimination_holds(uu, vv, up, a) for uu, vv in sols)
            verified = all(round_map(uu, vv, a, b) == (up, vp) for uu, vv in sols)
            rows.append(dict(m=m, system=t, budget=budget, nodes=st["nodes"],
                             solved=int(bool(sols)), exhausted=int(st["exhausted"]),
                             solution_verified=int(verified),
                             elimination_holds=int(elim), seconds=dt))
        med = statistics.median(r["nodes"] for r in rows if r["m"] == m)
        print(f"  [R3] m={m} median_nodes={med:.0f}", flush=True)
    return rows


def r3b_fit(rows, fit_from=8, extrapolate=(36, 48, 59, 67)):
    by_m: dict[int, list[int]] = {}
    for r in rows:
        by_m.setdefault(r["m"], []).append(r["nodes"])
    pts = [(m, log2(statistics.median(v))) for m, v in sorted(by_m.items()) if m >= fit_from]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    xbar, ybar = sum(xs) / len(xs), sum(ys) / len(ys)
    slope = sum((x - xbar) * (y - ybar) for x, y in zip(xs, ys)) / sum((x - xbar) ** 2 for x in xs)
    intercept = ybar - slope * xbar
    return dict(slope_bits_per_degree=slope, intercept=intercept,
                fitted_on=xs,
                medians={str(m): statistics.median(v) for m, v in sorted(by_m.items())},
                extrapolated_log2_nodes={str(m): slope * m + intercept for m in extrapolate})


def round_hardness_degree(target_bits: float, slope: float, intercept: float) -> int:
    m = 5
    while slope * m + intercept < target_bits:
        m += 1
    return m


def r9_end_to_end(cases=((7, 8), (9, 8), (9, 10), (11, 8))):
    rows = []
    for (m, n) in cases:
        inst = generate_cpwi_instance(n, m, seed_from("CPWI-R9-instance", m, n) % (1 << 62))
        rng = random.Random(seed_from("CPWI-R9-input", m, n))
        x = tuple(rng.randrange(2) for _ in range(n))
        y = cpwi_forward(x, inst)
        t0 = time.perf_counter()
        found, st = invert_backward(inst, y, max_solutions=1)
        dt = time.perf_counter() - t0
        ok = bool(found) and cpwi_forward(found[0], inst) == y
        rows.append(dict(m=m, n=n, seconds=dt, valid_preimage=int(ok),
                         planted_input_recovered=int(bool(found) and tuple(found[0]) == x),
                         expansions=st["expansions"], round_solves=st["round_solves"],
                         solver_nodes=st["round_nodes"],
                         budget_exhausted_solves=st["budget_exhausted_solves"],
                         elimination_checks=st["elimination_checks"],
                         elimination_failures=st["elimination_failures"],
                         planted_input_lsb_first="".join(map(str, x)),
                         recovered_input_lsb_first="".join(map(str, found[0])) if found else ""))
        print(f"  [R9] m={m} n={n} valid={ok} {dt:.1f}s solves={st['round_solves']}", flush=True)
    return rows


def solver_cross_check(m=5, trials=30):
    """Solver output equals exhaustive enumeration on random targets and on
    random (mostly unreachable) states."""
    group = alternating_group(m)
    rng = random.Random(seed_from("CPWI-RX-crosscheck", m))
    ok = 0
    for t in range(trials):
        a, b = random_even_permutation(m, rng), random_even_permutation(m, rng)
        if t % 2 == 0:
            u, v = random_even_permutation(m, rng), random_even_permutation(m, rng)
            up, vp = round_map(u, v, a, b)
        else:
            up, vp = random_even_permutation(m, rng), random_even_permutation(m, rng)
        exact = sorted(enumerate_round_preimages(up, vp, a, b, group))
        sols, st = solve_round(up, vp, a, b, max_solutions=10 ** 6, node_budget=10 ** 7)
        ok += int(sorted(sols) == exact and not st["exhausted"])
    return dict(m=m, trials=trials, agree=ok)


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def write_csv(path: Path, rows) -> None:
    rows = list(rows)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def latex_tables(summary: dict, e2e_rows) -> dict[str, str]:
    s = summary
    r1 = dict(s["R1"])
    r1.setdefault("6", dict(image_density=float("nan"), mean_preimages_reachable=float("nan")))
    rnd = (
        "\\begin{tabularx}{\\textwidth}{@{}>{\\raggedright\\arraybackslash}Xlll@{}}\n"
        "\\toprule\nQuantity & $m=5$ & $m=6$ & Random-map value \\\\\n\\midrule\n"
        f"Image density of $\\Phi_{{i,b}}$ & {r1['5']['image_density']:.3f} & {r1['6']['image_density']:.3f} & $1-e^{{-1}}=0.632$ \\\\\n"
        f"Mean preimages of a reachable state, producing branch & {r1['5']['mean_preimages_reachable']:.3f} & {r1['6']['mean_preimages_reachable']:.3f} & 2 \\\\\n"
        f"Mean preimages of a reachable state, other branch & {s['R2']['mean_preimages_other_branch']:.2f} & --- & 1 \\\\\n"
        f"Other branch solvable & {100 * s['R2']['fraction_other_branch_solvable']:.1f}\\% & --- & 63.2\\% \\\\\n"
        f"Backward children of a uniformly random state & {s['R2b']['mean_backward_children']:.2f} & --- & 2 \\\\\n"
        "\\bottomrule\n\\end{tabularx}\n")
    e2e = ("\\begin{tabular}{@{}rrrrrl@{}}\n\\toprule\n"
           "$m$ & $n$ & Time (s) & Round solves & Solver nodes & Planted input recovered \\\\\n\\midrule\n")
    for r in e2e_rows:
        e2e += (f"{r['m']} & {r['n']} & {r['seconds']:.1f} & {r['round_solves']} & "
                f"{r['solver_nodes']:,} & {'yes' if r['planted_input_recovered'] else 'no'} \\\\\n")
    e2e += "\\bottomrule\n\\end{tabular}\n"
    return {"round.tex": rnd, "e2e.tex": e2e}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--out", type=Path, default=Path(__file__).parent / "round_results")
    args = ap.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    (out / "latex_tables").mkdir(exist_ok=True)
    t0 = time.perf_counter()
    q = args.quick

    cross = solver_cross_check(trials=10 if q else 30)
    if cross["agree"] != cross["trials"]:
        raise AssertionError(f"solver disagrees with exhaustive enumeration: {cross}")
    print(f"  [RX] solver cross-check {cross['agree']}/{cross['trials']}", flush=True)

    r1 = r1_round_map_statistics((5,) if q else (5, 6), (3,) if q else (6, 2))
    r2 = r2_branch_statistics(trials=40 if q else 120)
    r2b = r2b_spurious_branching(trials=60 if q else 200)
    r3 = r3_solver_scaling((6, 7, 8, 9, 10) if q else (6, 7, 8, 9, 10, 11, 12, 13),
                           systems=3 if q else 5)
    fit = r3b_fit(r3)
    r9 = r9_end_to_end(((7, 8), (9, 8)) if q else ((7, 8), (9, 8), (9, 10), (11, 8)))

    write_csv(out / "round_map_statistics.csv", r1)
    write_csv(out / "branch_statistics.csv", r2)
    write_csv(out / "spurious_branching.csv", r2b)
    write_csv(out / "solver_scaling.csv", r3)
    write_csv(out / "end_to_end_inversion.csv", r9)

    def agg(rows, m, key):
        vals = [r[key] for r in rows if r["m"] == m]
        return statistics.fmean(vals) if vals else None

    summary = {
        "R1": {str(m): dict(maps=sum(r["m"] == m for r in r1),
                            image_density=agg(r1, m, "image_density"),
                            mean_preimages_reachable=agg(r1, m, "mean_preimages_reachable"))
               for m in sorted({r["m"] for r in r1})},
        "R2": dict(m=5, trials=len(r2),
                   mean_preimages_producing_branch=statistics.fmean(r["preimages_producing_branch"] for r in r2),
                   mean_preimages_other_branch=statistics.fmean(r["preimages_other_branch"] for r in r2),
                   fraction_other_branch_solvable=statistics.fmean(r["other_branch_solvable"] for r in r2),
                   random_map_values=dict(producing=2.0, other=1.0, other_solvable=1 - exp(-1))),
        "R2b": dict(m=5, trials=len(r2b),
                    mean_backward_children=statistics.fmean(r["backward_children"] for r in r2b),
                    fraction_dead=statistics.fmean(r["backward_children"] == 0 for r in r2b),
                    random_map_value=2.0),
        "R3": dict(systems_per_degree=5 if not q else 3, budget=300_000,
                   solved={str(m): sum(r["solved"] for r in r3 if r["m"] == m) for m in sorted({r["m"] for r in r3})},
                   exhausted={str(m): sum(r["exhausted"] for r in r3 if r["m"] == m) for m in sorted({r["m"] for r in r3})},
                   all_solutions_verified=all(r["solution_verified"] for r in r3),
                   all_elimination_checks_hold=all(r["elimination_holds"] for r in r3),
                   fit=fit,
                   round_hardness_degree={str(l): round_hardness_degree(l, fit["slope_bits_per_degree"], fit["intercept"])
                                          for l in (128, 192, 256)},
                   combined_attack_log2_cost={"(256,36)": 128 + fit["extrapolated_log2_nodes"]["36"],
                                              "(384,48)": 192 + fit["extrapolated_log2_nodes"]["48"],
                                              "(512,59)": 256 + fit["extrapolated_log2_nodes"]["59"]},
                   note="log2(nodes) = slope*m + intercept fitted on medians over m >= 8; "
                        "extrapolation beyond the measured range is an assumption, not a bound."),
        "R9": dict(cases=len(r9), all_valid=all(r["valid_preimage"] for r in r9),
                   all_planted_recovered=all(r["planted_input_recovered"] for r in r9),
                   elimination_failures=sum(r["elimination_failures"] for r in r9)),
        "solver_cross_check": cross,
        "environment": dict(python=sys.version, platform=platform.platform(),
                            script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                            reproduce_sha256=hashlib.sha256(Path(__file__).with_name("reproduce.py").read_bytes()).hexdigest(),
                            quick=q, wall_seconds=time.perf_counter() - t0,
                            timing_policy="Local elapsed times only; no hardware-normalised claims."),
    }
    (out / "round_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    for name, text in latex_tables(summary, r9).items():
        (out / "latex_tables" / name).write_text(text)

    # Revised parameter rows: n = 3*lambda (2*lambda plus a margin for the
    # matching phase), m = max(capacity degree, round-hardness degree).
    def capacity_degree(n, s=16):
        m = 5
        while 2 * (log2(math_factorial(m)) - 1) < n + s:
            m += 1
        return m
    prow = []
    for lam in (128, 192, 256):
        n = 3 * lam
        m_cap = capacity_degree(n)
        m_rnd = summary["R3"]["round_hardness_degree"][str(lam)]
        m = max(m_cap, m_rnd)
        prow.append(dict(target_bits=lam, input_bits_n=n, capacity_degree=m_cap,
                         round_hardness_degree=m_rnd, alternating_group_degree_m=m,
                         public_description_kib=(4 * n + 2) * m * (m - 1).bit_length() / 8 / 1024,
                         elementary_image_operations_upper_bound=6 * n * m,
                         basis="n = 3*lambda; m from the fitted round-solver cost curve; not a recommendation"))
    write_csv(out / "revised_parameter_table.csv", prow)
    print(f"wrote {out} in {time.perf_counter() - t0:.1f}s", flush=True)


def math_factorial(k: int) -> int:
    r = 1
    for i in range(2, k + 1):
        r *= i
    return r


if __name__ == "__main__":
    main()
