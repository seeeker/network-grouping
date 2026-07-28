# Client-pool grouping algorithm — implementation specification

**Audience:** an implementer (human or agent) building this from scratch. This file is
self-contained: everything needed to implement and verify the algorithm is here.
Context files (optional): `network-topology-reference.md` (full design narrative),
`grouping.py` (reference implementation), `test_grouping.py` (84-assertion suite),
`grouping-test-scenarios.md` (scenario matrix).

---

## 1. Problem statement

A tree-shaped network distributes a data set held in full by a **root controller
device (RCD)**. Clients (**CLD**) cannot hold the full set individually, but a group
("pool") of them can, each member holding a shard. Clients read from their pool first;
the RCD is a fallback that must be assumed able to fail. Therefore:

> **Invariant I1:** every client must belong to a pool large enough to reconstruct the
> full data set locally — or be explicitly reported as a defect. No client may silently
> depend on the RCD.

The algorithm's job: given the topology and pool-size parameters, partition all
clients into pools that satisfy I1 while minimizing cross-chain network traffic and
maximizing tolerance to individual client loss.

## 2. Topology model (input)

The physical hierarchy is RCD → optional ADD (area distribution device) →
daisy-chained CHDs (chain devices) → clients. For this algorithm, it reduces to:

```
Column  := one daisy chain of clients, ordered head → tail.
           The HEAD is the end nearest the chain's attachment point.
Junction := the attachment point of a column: an ADD id, or the literal
           token "RCD" for chains hanging directly off the root.
```

**Input schema** (any equivalent structure is fine):

```
columns: map<column_id, { junction: string, clients: [client_id, ...] }>
         # client list is head → tail order; may be empty
T:       int   # Target Pool Size — minimum clients that reconstruct the data set
M:       int   # Max Pool Size — hard cap (per client type; see §9.1)
allowDissolve: bool  # user flag, default false — see §6
```

**Output schema:**

```
pools:   [[client_id, ...], ...]   # every pool has T <= size <= M
defects: [[client_id, ...], ...]   # stranded clients, grouped as stranded
report:  feasibility info + trace  # see §7
```

**Postconditions to assert:** (a) every input client appears in exactly one pool or
one defect set; (b) every pool size is in `[T, M]`; (c) defects are empty iff the
total is partitionable AND no column was isolated beyond repair.

## 3. Core math

### 3.1 Partitionability

A count `n` is **partitionable** iff it can be written as a sum of parts each in
`[T, M]`. Test: some `k` in `[ceil(n/M) .. floor(n/T)]` satisfies `k*T <= n <= k*M`.

```
feasible_ks(n, T, M) = [ k in ceil(n/M) .. floor(n/T)  where  k*T <= n <= k*M ]
partitionable(n)     = feasible_ks(n, T, M) is non-empty     (n >= T required)
```

Example (T=5, M=6): reachable totals are 5, 6, 10, 11, 12, 15, 16, 17, 18, 20, …
— **13, 14, 19 are gaps.** If the grand total of clients sits in a gap, at least one
client is stranded *no matter what the algorithm does*. Detect this up front (§7).

### 3.2 Splitting sizes

Given `n` and a chosen `k`, sizes are near-equal: `base = n div k`, `extra = n mod k`
→ `extra` parts of `base+1` and `k-extra` parts of `base`. All parts land in `[T, M]`
by construction when `k` is feasible.

**Choosing k when several are feasible:** pick the **smallest** k (fewest, largest
pools). Rationale: a pool above `T` tolerates client loss (size can drop to `T` and
stay complete); this is the only redundancy lever in scope (priority stack, §8).

**Ordering the sizes:** when the unit is a merged virtual chain (§5), put the
**larger** sizes at the seam end (start of the linearization) so the cross-junction
pool carries slack. This is a deliberate, documented trade — see §9.2 before locking it.

### 3.3 Tree distance (proximity metric)

```
dist(a, b):
  same column:        |pos_a - pos_b|                    # hops along the chain
  same junction:      (pos_a + 1) + (pos_b + 1)          # up to junction, down
  different junction: (pos_a + 1) + (pos_b + 1) + C      # via the RCD; C = const > 0
```

`pos` is the 0-based index from the column head. The constant C only needs to make
cross-junction strictly costlier than same-junction; exact hop counts are optional
precision. Distance from a *set* (fragment/pool) to a client = min over members.

## 4. Algorithm overview

Three phases. Phase 1 does the heavy lifting; Phase 2 is a fallback; Phase 3 is
cosmetic.

```
Phase 0  Annotate clients (column, pos, junction) + deficiency census
         + grand-total feasibility check.
Phase 1  Build units (virtual chains), cut each with flexible k.
Phase 2  FALLBACK: complete leftover fragments via donors; then the
         user-controlled dissolve; else flag defects.
Phase 3  Optional: distribute any remaining spares to nearest pools below M.
```

**Design principle (why the census exists):** never chunk a column in isolation when
a deficient column is waiting nearby. Committing early produces "Franken-pools" —
complete but maximally-spanning pools assembled by greedy repair (§10, case 7 shows
the failure). Deciding merges *before* cutting reaches the global optimum cheaply.

## 5. Phase 1 — census, virtual chains, flexible-k cut

### 5.1 Census

```
deficient = [ col for col in columns if 0 < |col| < T ]
```

Empty columns are legal (a CHD may carry zero clients); skip them entirely.

### 5.2 Merge rule (mergeability boundary)

A deficient column may merge with **at most one partner column sharing the same
junction** (same ADD, or both direct off the RCD). Columns under *different*
junctions are NEVER merged in Phase 1 — forcing that combination through Phase 2
keeps the expensive cross-ADD decision explicit rather than hidden in a linearization.

Partner selection, in order:
1. Another **deficient** column at the same junction (resolves two deficits at once).
2. A **complete** column at the same junction.
3. Accept a partner **only if** `partitionable(|deficient| + |partner|)`. If merging
   would produce an unpartitionable unit, do NOT merge — send the deficient column to
   Phase 2 instead. (This keeps `allowDissolve` semantics meaningful: the strict/
   dissolve decision stays with the user rather than being pre-empted by a salvage
   split. See §10 case 4 vs case 7 for the two behaviors this preserves.)
4. No qualifying partner → the deficient column becomes a Phase 2 fragment whole.

Each column participates in at most one merge (pairwise only — see §9.4 for the
known limitation with 3+ deficient columns).

### 5.3 Seam ordering (linearization)

A merged pair becomes one **virtual chain**, linearized as a walk through the
junction:

```
reversed(deficient column)  ++  partner column (head → tail)
   i.e.  deficient tail → deficient head → [junction] → partner head → partner tail
```

The junction is the **seam** — the cheapest stitch point. This guarantees the
deficient column's clients group with the partner's *head* clients (physically
adjacent through the junction), never its far tail.

Worked target (the case that motivated the design): column1 = clients 1–14,
column2 = [15], T=5, M=6. Linearization: `15, 1, 2, …, 14`. Cut k=3, sizes 5+5+5:

```
[15, 1, 2, 3, 4]   [5, 6, 7, 8, 9]   [10, 11, 12, 13, 14]
```

Only client 15 crosses the junction, and only to reach the clients immediately on
the other side. (Contrast with the greedy-repair result in §10 case 7.)

### 5.4 Cutting

For every unit (merged virtual chain, or a plain unmerged column):

```
n  = |unit|
ks = feasible_ks(n, T, M)
if ks non-empty:
    k = min(ks)
    sizes = split_sizes(n, k)         # larger sizes at seam end if merged
    emit contiguous pools per sizes
else:                                  # unpartitionable unit (plain columns only,
                                       # merged units were pre-checked in 5.2)
    cover as much as possible: k = floor(n/T); pool k contiguous parts sized
    within [T, M] (max coverage = min(n, k*M)); the sub-T remainder (taken from
    the tail end) becomes a Phase 2 fragment.
```

Leftover distribution falls out of split_sizes automatically: remainders top pools
*up* toward M, never form a sub-T group, and pools are always contiguous runs.

## 6. Phase 2 — fallback: donors, then dissolve, then defect

Input: fragments (each `< T`). Process smallest first (hardest to complete).

### 6.1 Donor loop

Candidates for a fragment F:
- members of **other fragments**;
- **surplus** clients of formed pools — a pool has surplus iff `size > T`
  (it can shed while staying complete). **Headroom (`size < M`) is NOT surplus** —
  headroom lets a pool receive, surplus lets it give. Confusing these two is the
  most likely implementation bug (see §10 cases 4 vs 5).
- To preserve contiguity, only a pool's **edge members** (first/last in its run)
  are sheddable.

Sort candidates by `dist(F, candidate)` ascending; tiebreak: fragment members
before surplus (draining two deficits beats shrinking a healthy pool). Absorb one
at a time, re-ranking after each move (distances change as F grows), until
`|F| >= T` or `|F| = M` or candidates are exhausted. If a donation empties another
fragment, remove it. A donating pool must never drop below T.

Completed F → emit as a pool.

### 6.2 Dissolve fallback (user-controlled)

If F cannot reach T and `allowDissolve` is **true**: push F's members
**individually, nearest-first**, into existing pools with headroom (`size < M`),
each to its nearest such pool. Members with no reachable headroom anywhere → defect.

If `allowDissolve` is **false**: the whole fragment becomes a defect, **kept
together**. Rationale for the default: a stranded-but-intact fragment preserves
grouping intent — when the topology is later fixed (clients added), the fragment
becomes its intended local pool without regrouping. Dissolving scatters it and
requires a re-run to undo. The user opts *into* the lossier action.

### 6.3 Defect

A defect is not a resting state — it is a region that cannot survive an RCD outage.
Always emit it in the report with the feasibility remedy (§7).

## 7. Reporting

Compute up front and attach to output:

```
total          = count of all clients
partitionable  = partitionable(total)
nearest_down   = largest  n' <= total with partitionable(n')
nearest_up     = smallest n' >= total with partitionable(n')
```

When defects exist, the report should state the remedy in operational terms:
"add (nearest_up - total) clients" and/or "lower T to <t'>" where t' is the largest
target making the total partitionable. Example: 19 clients at T=5/M=6 → "1 client
away from clean (20)". This turns the defect flag from an error into a
capacity-planning signal. Also emit a per-step trace (merge decisions, donor moves,
dissolve placements) — invaluable for debugging and for the divergence checks in §10.

## 8. Priority stack (conflict resolution)

When choices conflict, resolve in this strict order:

1. **Completeness** — every client in a pool of `>= T`, or an explicit defect.
2. **Loss tolerance** — prefer pools above `T` (smallest feasible k; leftovers top up).
3. **Locality** — minimize cross-chain/cross-junction span, subject to 1 and 2.

Locality is deliberately *last*. It governs partner choice and donor order, but never
justifies leaving a client below T or shrinking slack that rule 2 created.

## 9. Open decisions (implement the default, flag the fork)

These are unresolved in the spec. Implement the stated default; make each one
cheap to flip; surface them to whoever owns the requirements.

### 9.1 Mixed client types
`M` is per client type; a mixed pool's cap is `min` over member types. Default:
compute it that way. Untested — no real type data yet. Watch for: a merge that
*lowers* M enough to change feasibility of the merged unit.

### 9.2 Seam-size trade
Current rule gives the seam pool the *larger* size (slack where repair is
costliest). This increases cross-junction member-pairs vs giving it the smaller
size (e.g. 10+3 @ T=4: seam of 5 → 6 cross pairs, seam of 4 → 3). If traffic
should win over slack, reverse the size ordering. Either way: pin with a test.

### 9.3 Pool immutability
The donor loop and dissolve both mutate formed pools. If pools must be immutable
once formed (stability/hysteresis), donors can only come from fragments and
dissolve must run pre-finalization as a re-chunk. Default: mutation allowed.

### 9.4 Multi-deficient pairing order
Pairing is greedy (smallest deficient first). With 3+ deficient columns at one
junction, greedy order can strand clients that a different pairing would save
(pairing A+B leaves C infeasible while A+C and B+partner recover everyone).
Default: greedy; production should exhaustively try pairings when deficient
count at a junction exceeds 2 (the search space is tiny).

### 9.5 CLD daisy-chains
Clients may chain off clients (CLD → CLD). Their `pos` in the proximity metric is
undefined. Proposed default: a chained client sits at `parent.pos` + chain depth.
Decide before topologies with client chains go live.

## 10. Verification cases (implement these as tests first)

All with M=6. `→` denotes required output. These are the ground-truth cases the
reference suite asserts; an implementation disagreeing with any of them is wrong
(except where §9 flags a deliberate fork).

| # | Setup | T | flag | Required outcome |
|---|-------|---|------|------------------|
| 1 | one column of 8 | 4 | — | pools [4,4] |
| 2 | one column of 10 | 4 | — | pools [5,5] (leftovers top up, never a sub-T group) |
| 3 | one column of 12 | 5 | — | pools [6,6] (smallest k wins over other cuts) |
| 4 | one column of 13 | 4 | — | pools [4,4,5] (flexible k; no trim, no fragment) |
| 5 | cols 1–10 and 11–13, same ADD | 4 | — | 0 defects; one pool contains all of {11,12,13} plus column-1 HEAD clients only |
| 6 | cols 1–10 and 11–13, same ADD | 5 | false | pools [5,5]; defect **[11,12,13] together** (13 unpartitionable; no surplus exists — both pools at exactly T) |
| 7 | cols 1–14 and [15], same ADD | 5 | — | pools **exactly** [15,1–4], [5–9], [10–14] |
| 8 | cols 1–10 and 11–13, same ADD | 5 | true | pools [6,6]; defect = one client |
| 9 | cols 1–15 and 16–19, same ADD | 5 | true | pools [6,6,6]; defect = one client (19 is a gap; 1 stranded is the forced minimum) |
| 10 | cols 1–15 and 16–19, same ADD | 5 | false | pools [5,5,5]; defect [16,17,18,19] together |
| 11 | cols of 3, 2, 12, same ADD | 5 | — | 0 defects; {1..5} = one pool (the two deficients merged with each other, not with the 12) |
| 12 | cols [1–3] under ADD1, [4–6] under ADD2 | 5 | true | one pool of 6 (via Phase 2 donors + dissolve — NEVER via a cross-ADD virtual chain) |
| 13 | cols [1–3] and [4–12], both junction=RCD | 5 | — | 0 defects (RCD is a junction like any ADD) |
| 14 | one empty column + one column of 5 | 5 | — | pools [5]; empty column ignored |
| 15 | a single lone client | 5 | either | defect [that client] (dissolve needs an existing pool with headroom; none exists) |
| 16 | empty topology | 5 | — | no pools, no defects |

Also assert globally, on every case: coverage (each client in exactly one pool or
defect), size bounds, and — for feasible totals with same-junction columns — zero
defects.

## 11. Reference-implementation pointers

`grouping.py` in this repository implements everything above (~200 lines, stdlib
only); `test_grouping.py` runs 84 assertions over the cases in §10 plus invariant
checks. Use them as an oracle: run both implementations on random topologies and
diff outputs. Divergences are acceptable only where §9 marks a fork — and then only
after the fork is decided and pinned.
