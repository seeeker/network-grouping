"""Scenario test suite for the grouping algorithm.

Categories:
  A. Single-column basics (even split, leftover top-up, exact T, exact M)
  B. Flexible-k behavior (avoiding needless trims)
  C. Virtual-chain merges (deficient + partner, seam ordering)
  D. Donor fallback (surplus exists)
  E. No-donor wall + allowDissolve both ways
  F. Infeasible totals (forced defects, minimum stranding)
  G. Multi-deficient columns, same junction
  H. Deficient columns under DIFFERENT junctions (no virtual chain)
  I. Direct-off-RCD junction merges
  J. Degenerate inputs (empty column, single isolated client, tiny topology)
  K. Shard assignment (Phase 4): coverage invariant, CHD diversity on/off,
     cross-pool diversity on straddling CHDs, duplicate distribution
"""

from grouping import group_clients, feasible_ks, nearest_feasible_totals

PASS, FAIL = 0, []


def col(junction, ids):
    return {"junction": junction, "clients": list(ids)}


def check(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(f"{name}: {detail}")


def invariants(name, res, columns, T, M, expect_defect_count=None):
    all_ids = [c for spec in columns.values() for c in spec["clients"]]
    placed = [c for p in res.pools for c in p] + [c for d in res.defects for c in d]
    check(f"{name}/coverage", sorted(placed) == sorted(all_ids),
          f"placed {sorted(placed)} != all {sorted(all_ids)}")
    for p in res.pools:
        check(f"{name}/size", T <= len(p) <= M, f"pool {p} size {len(p)}")
    if expect_defect_count is not None:
        n_def = sum(len(d) for d in res.defects)
        check(f"{name}/defects", n_def == expect_defect_count,
              f"stranded {n_def} != expected {expect_defect_count} "
              f"(defects={res.defects})")


def run():
    # ---------- A. single-column basics ----------
    r = group_clients({"c1": col("ADD1", range(1, 9))}, T=4, M=6)
    invariants("A1 8@T4", r, {"c1": col("ADD1", range(1, 9))}, 4, 6, 0)
    check("A1/shape", sorted(map(len, r.pools)) == [4, 4], r.pools)

    r = group_clients({"c1": col("ADD1", range(1, 11))}, T=4, M=6)
    check("A2 10@T4 topped", sorted(map(len, r.pools)) == [5, 5], r.pools)

    r = group_clients({"c1": col("ADD1", range(1, 6))}, T=5, M=6)
    check("A3 exact-T", r.pools == [[1, 2, 3, 4, 5]], r.pools)

    r = group_clients({"c1": col("ADD1", range(1, 7))}, T=5, M=6)
    check("A4 exact-M", r.pools == [[1, 2, 3, 4, 5, 6]], r.pools)

    r = group_clients({"c1": col("ADD1", range(1, 13))}, T=5, M=6)
    check("A5 12@T5 prefers slack", sorted(map(len, r.pools)) == [6, 6], r.pools)

    # ---------- B. flexible-k avoids needless trims ----------
    r = group_clients({"c1": col("ADD1", range(1, 14))}, T=4, M=6)
    invariants("B1 13@T4", r, {"c1": col("ADD1", range(1, 14))}, 4, 6, 0)
    check("B1/shape", sorted(map(len, r.pools)) == [4, 4, 5], r.pools)

    r = group_clients({"c1": col("ADD1", range(1, 17))}, T=5, M=6)
    check("B2 16@T5", sorted(map(len, r.pools)) == [5, 5, 6], r.pools)

    # ---------- C. virtual-chain merges ----------
    cols_c1 = {"c1": col("ADD1", range(1, 15)), "c2": col("ADD1", [15])}
    r = group_clients(cols_c1, T=5, M=6)
    invariants("C1 14+1@T5", r, cols_c1, 5, 6, 0)
    check("C1/target-shape",
          [15, 1, 2, 3, 4] in r.pools and [5, 6, 7, 8, 9] in r.pools
          and [10, 11, 12, 13, 14] in r.pools, r.pools)

    cols_c2 = {"c1": col("ADD1", range(1, 11)), "c2": col("ADD1", [11, 12, 13])}
    r = group_clients(cols_c2, T=4, M=6)
    invariants("C2 10+3@T4", r, cols_c2, 4, 6, 0)
    seam = next(p for p in r.pools if 11 in p)
    check("C2/seam-holds-col2", all(x in seam for x in (11, 12, 13)), r.pools)
    check("C2/seam-uses-head",
          all(x in seam for x in (11, 12, 13)) and max(seam) <= 13 and
          all((x <= 2 or x >= 11) for x in seam),
          f"seam {seam} should draw from column head, not tail")

    # ---------- D. donor fallback with surplus ----------
    cols_d = {"c1": col("ADD1", range(1, 13)), "c2": col("ADD1", [13, 14, 15, 16])}
    r = group_clients(cols_d, T=5, M=6)
    invariants("D1 12+4@T5", r, cols_d, 5, 6, 0)

    # ---------- E. no-donor wall + dissolve flag ----------
    cols_e = {"c1": col("ADD1", range(1, 11)), "c2": col("ADD1", [11, 12, 13])}
    r = group_clients(cols_e, T=5, M=6, allow_dissolve=False)
    invariants("E1 10+3@T5 strict", r, cols_e, 5, 6, 3)
    check("E1/frag-together", r.defects == [[11, 12, 13]], r.defects)

    r = group_clients(cols_e, T=5, M=6, allow_dissolve=True)
    invariants("E2 10+3@T5 dissolve", r, cols_e, 5, 6, 1)
    check("E2/pools-max", sorted(map(len, r.pools)) == [6, 6], r.pools)

    cols_e3 = {"c1": col("ADD1", range(1, 16)), "c2": col("ADD1", [16, 17, 18, 19])}
    r = group_clients(cols_e3, T=5, M=6, allow_dissolve=False)
    invariants("E3 15+4@T5 strict", r, cols_e3, 5, 6, 4)
    r = group_clients(cols_e3, T=5, M=6, allow_dissolve=True)
    invariants("E4 15+4@T5 dissolve", r, cols_e3, 5, 6, 1)
    check("E4/all-pools-M", sorted(map(len, r.pools)) == [6, 6, 6], r.pools)

    # ---------- F. infeasibility math ----------
    check("F1 13@T5 infeasible", feasible_ks(13, 5, 6) == [])
    check("F2 19@T5 infeasible", feasible_ks(19, 5, 6) == [])
    check("F3 nearest(13)", nearest_feasible_totals(13, 5, 6) == (12, 15))
    check("F4 nearest(19)", nearest_feasible_totals(19, 5, 6) == (18, 20))

    # ---------- G. multi-deficient, same junction ----------
    cols_g = {"a": col("ADD1", [1, 2, 3]), "b": col("ADD1", [4, 5]),
              "c": col("ADD1", range(6, 18))}
    r = group_clients(cols_g, T=5, M=6)
    invariants("G1 3+2+12@T5", r, cols_g, 5, 6, 0)
    check("G1/deficients-merged",
          any(set(p) == {1, 2, 3, 4, 5} for p in r.pools), r.pools)

    # ---------- H. deficient columns under DIFFERENT junctions ----------
    cols_h = {"a": col("ADD1", [1, 2, 3]), "b": col("ADD2", [4, 5, 6])}
    r = group_clients(cols_h, T=5, M=6, allow_dissolve=False)
    invariants("H1 cross-ADD strict", r, cols_h, 5, 6, 1)
    r = group_clients(cols_h, T=5, M=6, allow_dissolve=True)
    invariants("H2 cross-ADD dissolve", r, cols_h, 5, 6, 0)
    check("H2/single-pool", sorted(map(len, r.pools)) == [6], r.pools)

    # ---------- I. direct-off-RCD junction ----------
    cols_i = {"a": col("RCD", [1, 2, 3]), "b": col("RCD", range(4, 13))}
    r = group_clients(cols_i, T=5, M=6)
    invariants("I1 RCD-junction merge", r, cols_i, 5, 6, 0)

    # ---------- J. degenerate inputs ----------
    r = group_clients({"a": col("ADD1", []), "b": col("ADD1", range(1, 6))},
                      T=5, M=6)
    invariants("J1 empty col ignored", r,
               {"b": col("ADD1", range(1, 6))}, 5, 6, 0)

    r = group_clients({"a": col("ADD1", [1])}, T=5, M=6, allow_dissolve=False)
    invariants("J2 lone client strict", r, {"a": col("ADD1", [1])}, 5, 6, 1)
    r = group_clients({"a": col("ADD1", [1])}, T=5, M=6, allow_dissolve=True)
    invariants("J3 lone client dissolve (no pools -> still defect)", r,
               {"a": col("ADD1", [1])}, 5, 6, 1)

    r = group_clients({}, T=5, M=6)
    check("J4 empty topology", r.pools == [] and r.defects == [])

    # ---------- K. shard assignment ----------
    def pool_shards(res, pool):
        return [res.shards[c] for c in pool]

    def chd_map(columns):
        m = {}
        for col_id, spec in columns.items():
            raw = spec["clients"]
            groups = raw if raw and isinstance(raw[0], (list, tuple)) else [[x] for x in raw]
            for gi, g in enumerate(groups):
                for cid in g:
                    m[cid] = f"{col_id}/chd{gi}"
        return m

    # K1/K2: every pool covers all shards 1..T, both modes
    cols_k = {"c1": col("ADD1", [[1, 2, 3], [4, 5, 6], [7, 8], [9, 10]])}
    for div in (False, True):
        r = group_clients(cols_k, T=5, M=6, chd_shard_diversity=div)
        for p in r.pools:
            check(f"K1 coverage div={div}", set(pool_shards(r, p)) == set(range(1, 6)),
                  f"pool {p} shards {pool_shards(r, p)}")

    # K3: duplicates distributed round-robin (pool of 6 at T=5 -> shard 1 twice)
    r = group_clients({"c1": col("ADD1", range(1, 7))}, T=5, M=6)
    counts = sorted(__import__("collections").Counter(r.shards.values()).values())
    check("K3 duplicate spread", counts == [1, 1, 1, 1, 2], r.shards)

    # K4: diversity ON -> a CHD gets max distinct shards. T=3, pool of 6,
    # two CHDs of 3: each CHD should hold {1,2,3}.
    cols_k4 = {"c1": {"junction": "ADD1", "clients": [[1, 2, 3], [4, 5, 6]]}}
    r = group_clients(cols_k4, T=3, M=6, chd_shard_diversity=True)
    cm = chd_map(cols_k4)
    per_chd = {}
    for cid, s in r.shards.items():
        per_chd.setdefault(cm[cid], []).append(s)
    for chd, sh in per_chd.items():
        check("K4 diverse CHD", len(set(sh)) == 3, f"{chd}: {sh}")

    # K5: diversity OFF on same setup -> at least one CHD repeats a shard
    r = group_clients(cols_k4, T=3, M=6, chd_shard_diversity=False)
    per_chd = {}
    for cid, s in r.shards.items():
        per_chd.setdefault(cm[cid], []).append(s)
    check("K5 non-diverse repeats", any(len(set(sh)) < len(sh) for sh in per_chd.values()),
          per_chd)

    # K6: cross-pool diversity on a straddling CHD. Column of 10 @ T=5 ->
    # pools [1-5],[6-10]; CHD layout [1,2,3,4],[5,6],[7,8,9,10] puts 5 (pool A)
    # and 6 (pool B) on one CHD; diversity should give them different shards.
    cols_k6 = {"c1": {"junction": "ADD1",
                      "clients": [[1, 2, 3, 4], [5, 6], [7, 8, 9, 10]]}}
    r = group_clients(cols_k6, T=5, M=6, chd_shard_diversity=True)
    check("K6 straddle distinct", r.shards[5] != r.shards[6],
          f"5->{r.shards[5]}, 6->{r.shards[6]}")

    # K7: flat input (no CHD info) is legal; coverage still holds
    r = group_clients({"c1": col("ADD1", range(1, 11))}, T=4, M=6,
                      chd_shard_diversity=True)
    for p in r.pools:
        check("K7 flat coverage", set(pool_shards(r, p)) == set(range(1, 5)),
              pool_shards(r, p))

    # K8: defect clients get no shard assignment
    r = group_clients({"c1": col("ADD1", [1, 2, 3])}, T=5, M=6)
    check("K8 defects unsharded", r.shards == {} and r.defects == [[1, 2, 3]],
          (r.shards, r.defects))

    print(f"PASS: {PASS}")
    if FAIL:
        print(f"FAIL: {len(FAIL)}")
        for f in FAIL:
            print("  -", f)
    else:
        print("FAIL: 0")
    return len(FAIL)


if __name__ == "__main__":
    raise SystemExit(run())
