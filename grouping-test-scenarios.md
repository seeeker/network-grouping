# Grouping algorithm — test scenario matrix

Companion to `network-topology-reference.md`. Every scenario below is implemented and
passing in `test_grouping.py` against the reference implementation `grouping.py`
(84 assertions, 0 failures). Parameters are `T` = Target Pool Size, `M` = 6 unless noted.

## A. Single-column basics

| # | Setup | T | Expected | Exercises |
|---|-------|---|----------|-----------|
| A1 | 8 clients | 4 | [4, 4] | even split, best case |
| A2 | 10 clients | 4 | [5, 5] | leftover top-up, never a sub-T group |
| A3 | 5 clients | 5 | [5] | column exactly at T |
| A4 | 6 clients | 5 | [6] | column exactly at M |
| A5 | 12 clients | 5 | [6, 6] | flexible k prefers fewer/larger pools (slack per priority-stack rule 2) over [4×3 → invalid] / [5,5,+2 frag] |

## B. Flexible k avoids needless trims

| # | Setup | T | Expected | Exercises |
|---|-------|---|----------|-----------|
| B1 | 13 clients | 4 | [4, 4, 5] | old fixed `⌊n/T⌋` would over-chunk; flexible k splits cleanly |
| B2 | 16 clients | 5 | [5, 5, 6] | k chosen from feasible range, sizes distributed evenly |

## C. Virtual-chain merges (deficient + same-junction partner)

| # | Setup | T | Expected | Exercises |
|---|-------|---|----------|-----------|
| C1 | col1 = 1–14, col2 = [15], same ADD | 5 | **[15,1–4], [5–9], [10–14]** | the Franken-pool fix: census + seam ordering + flexible k reach the global optimum |
| C2 | col1 = 1–10, col2 = [11–13], same ADD | 4 | seam pool holds all of col2 + col1 **head** clients | seam group stitches at the junction, never the far tail |

> **Observed divergence (C2):** the virtual-chain design yields seam pool `[13,12,11,1,2]`
> (size 5 — the "seam gets the larger size" cut rule), where the older donor-era worked
> example produced `[1,11,12,13]` (size 4, fewer cross-junction member-pairs: 3 vs 6).
> This is the documented slack-vs-traffic trade in "Choosing the cut": the current rule
> buys the seam group one client of loss tolerance at the cost of extra cross-junction
> pairs. Flip `seam_larger` if traffic should win.

## D. Donor fallback (surplus exists)

| # | Setup | T | Expected | Exercises |
|---|-------|---|----------|-----------|
| D1 | col1 = 1–12, col2 = 13–16, same ADD | 5 | all pooled, 0 defects (N=16 feasible → virtual chain) | deficit-of-one resolved without dissolve |

## E. No-donor wall + `allowDissolve`

| # | Setup | T | Flag | Expected | Exercises |
|---|-------|---|------|----------|-----------|
| E1 | col1 = 1–10, col2 = 11–13 | 5 | false | [5, 5] + defect **[11,12,13] kept together** | strict mode preserves grouping intent |
| E2 | same | 5 | true | [6, 6] + defect [13] | dissolve salvages to the arithmetic minimum |
| E3 | col1 = 1–15, col2 = 16–19 | 5 | false | [5,5,5] + defect [16–19] | headroom exists but surplus does not (headroom ≠ surplus) |
| E4 | same | 5 | true | [6,6,6] + defect [one client] | dissolve showcase: all pools reach M, minimum stranding |

## F. Infeasibility math (unit-level)

| # | Check | Expected |
|---|-------|----------|
| F1 | 13 partitionable at T=5, M=6? | no — reachable totals are 5, 6, 10–12, 15–18, … |
| F2 | 19 partitionable at T=5, M=6? | no — 3 parts max 18, 4 parts min 20 |
| F3 | nearest feasible to 13 | (12 down, 15 up) → "add 2 clients or lower T" |
| F4 | nearest feasible to 19 | (18 down, 20 up) → "**one** client away from clean" |

## G. Multiple deficient columns, same junction

| # | Setup | T | Expected | Exercises |
|---|-------|---|----------|-----------|
| G1 | cols of 3, 2, and 12 under one ADD | 5 | {1–5} as one pool (the two deficients merged), 12 → [6, 6] | deficient-prefers-deficient partner rule; the greedy pairing risk flagged in the doc |

## H. Deficient columns under different junctions (no virtual chain allowed)

| # | Setup | T | Flag | Expected | Exercises |
|---|-------|---|------|----------|-----------|
| H1 | [1–3] under ADD1, [4–6] under ADD2 | 5 | false | one pool of 5 via donors + defect [1] | cross-ADD merge stays explicit in Phase 2; mergeability boundary holds |
| H2 | same | 5 | true | single pool of 6, 0 defects | donors + dissolve together recover the feasible total |

## I. Direct-off-RCD junction

| # | Setup | T | Expected | Exercises |
|---|-------|---|----------|-----------|
| I1 | [1–3] and [4–12], both direct off the RCD | 5 | all pooled, 0 defects | "RCD" is a junction like any ADD for mergeability |

## J. Degenerate inputs

| # | Setup | Expected | Exercises |
|---|-------|----------|-----------|
| J1 | one empty column + one column of 5 | empty column ignored, [5] | 0-client columns are legal (CHDs may have 0 CLDs) |
| J2 | a single lone client, strict | defect [1] | total < T with no pools anywhere |
| J3 | a single lone client, dissolve | still defect [1] | dissolve needs a pool with headroom to exist |
| J4 | empty topology | no pools, no defects | vacuous case |

## Scenarios covered by design but worth adding when the spec settles

- **Mixed client types** (per-type `M` lowering a merged unit's cap) — the pseudocode
  computes `M = min over member types`, untested until real type data exists.
- **Multi-deficient pairing order** — G1 passes, but three-way cases where pairing
  order changes feasibility (e.g. sizes 2, 3, 4 with T=5: pairing 2+3 leaves 4 stranded
  while 2+4 and 3+... ) should get exhaustive-pairing treatment if they occur in practice.
- **Pool immutability / stability** (open decision) — no tests until decided; donor
  and dissolve tests would change under an immutable-pools rule.
- **Client daisy-chains (CLD → CLD)** — position/distance of chained clients is not yet
  defined in the proximity metric; tests pending that definition.
- **Mirror mode** — out of scope per the reference doc.
