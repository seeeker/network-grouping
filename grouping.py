"""Reference implementation of the client-pool grouping algorithm.

Implements the census -> virtual chain -> flexible-k design with the
donor/dissolve fallback (Phase 2), per network-topology-reference.md.

Topology input: {column_id: {"junction": str, "clients": [ids head->tail]}}
The junction is the shared attachment point: an ADD id, or "RCD" for
chains hanging directly off the root controller device.
"""

from math import ceil, floor
from dataclasses import dataclass, field


@dataclass
class Result:
    pools: list = field(default_factory=list)      # list of lists of client ids
    defects: list = field(default_factory=list)    # list of lists (stranded sets)
    notes: list = field(default_factory=list)      # human-readable trace
    feasibility: dict = field(default_factory=dict)


def feasible_ks(n, t, m):
    """Group counts k such that n splits into k parts each in [t, m]."""
    if n < t:
        return []
    return [k for k in range(ceil(n / m), floor(n / t) + 1) if k * t <= n <= k * m]


def split_sizes(n, k, seam_larger=True):
    """n into k near-equal parts; larger parts first (seam end) by default."""
    base, extra = divmod(n, k)
    sizes = [base + 1] * extra + [base] * (k - extra)
    if not seam_larger:
        sizes.reverse()
    return sizes


def nearest_feasible_totals(n, t, m):
    """(down, up): nearest partitionable totals at or below / above n."""
    def ok(x):
        return bool(feasible_ks(x, t, m)) if x > 0 else False
    down = next((x for x in range(n, 0, -1) if ok(x)), None)
    up = next(x for x in range(n, n + m + t + 1) if ok(x))
    return down, up


class _Client:
    __slots__ = ("cid", "col", "pos", "junction")

    def __init__(self, cid, col, pos, junction):
        self.cid, self.col, self.pos, self.junction = cid, col, pos, junction


def _tree_distance(a, b):
    """Hop distance between two clients (schematic but order-correct)."""
    if a.col == b.col:
        return abs(a.pos - b.pos)
    if a.junction == b.junction:
        return (a.pos + 1) + (b.pos + 1)          # up to shared junction, down
    return (a.pos + 1) + (b.pos + 1) + 4          # via RCD between junctions


def _frag_distance(frag, client):
    return min(_tree_distance(m, client) for m in frag)


def group_clients(columns, T, M, allow_dissolve=False):
    res = Result()
    # ---- Phase 0: annotate + census -------------------------------------
    clients = {}
    cols = {}
    for col_id, spec in columns.items():
        members = []
        for i, cid in enumerate(spec["clients"]):
            c = _Client(cid, col_id, i, spec["junction"])
            clients[cid] = c
            members.append(c)
        if members:
            cols[col_id] = members

    total = len(clients)
    down, up = nearest_feasible_totals(total, T, M) if total else (None, None)
    res.feasibility = {"total": total, "partitionable": down == total,
                       "nearest_down": down, "nearest_up": up}

    deficient = [cid for cid, mem in cols.items() if len(mem) < T]
    res.notes.append(f"census: deficient columns = {deficient or 'none'}")

    # ---- Phase 1: virtual chains + flexible-k cut -----------------------
    # units: list of linearized client lists (seam-ordered where merged)
    consumed = set()
    units = []
    fragments = []

    for dcol in sorted(deficient, key=lambda c: len(cols[c])):
        if dcol in consumed:
            continue
        junction = cols[dcol][0].junction
        # partner preference: other deficient cols at same junction first,
        # then complete cols; accept only if merged N is partitionable
        candidates = (
            [c for c in deficient if c != dcol and c not in consumed
             and cols[c][0].junction == junction]
            + [c for c in cols if c not in deficient and c not in consumed
               and cols[c][0].junction == junction]
        )
        partner = next(
            (p for p in candidates
             if feasible_ks(len(cols[dcol]) + len(cols[p]), T, M)), None)
        if partner is None:
            fragments.append(list(cols[dcol]))
            consumed.add(dcol)
            res.notes.append(f"{dcol}: no feasible same-junction partner -> fragment")
            continue
        # seam ordering: deficient tail->head, junction, partner head->tail
        chain = list(reversed(cols[dcol])) + list(cols[partner])
        units.append(("merged", chain))
        consumed.update((dcol, partner))
        res.notes.append(f"{dcol} merged with {partner} via {junction} "
                         f"(virtual chain of {len(chain)})")

    for col_id, members in cols.items():
        if col_id not in consumed:
            units.append(("plain", list(members)))

    pools = []
    for kind, chain in units:
        n = len(chain)
        ks = feasible_ks(n, T, M)
        if ks:
            k = ks[0]                                # smallest k -> largest pools
            sizes = split_sizes(n, k, seam_larger=(kind == "merged"))
            i = 0
            for s in sizes:
                pools.append(chain[i:i + s])
                i += s
        else:                                        # unpartitionable unit
            k = max(floor(n / T), 0)
            i = 0
            covered = min(n, k * M)
            # cover as much as possible with parts in [T, M]
            part_sizes = split_sizes(covered, k) if k else []
            for s in part_sizes:
                pools.append(chain[i:i + s])
                i += s
            if i < n:
                fragments.append(chain[i:])
                res.notes.append(
                    f"unit of {n} unpartitionable -> {n - i} client(s) to Phase 2")

    # ---- Phase 2 (fallback): donors, then dissolve ----------------------
    fragments.sort(key=len)
    while fragments:
        F = fragments.pop(0)
        if len(F) >= T:                              # can happen after donation
            pools.append(F)
            continue

        def surplus_edges():
            """Sheddable edge members of pools above T (edges keep contiguity)."""
            out = []
            for p in pools:
                if len(p) > T:
                    out.append((p, p[0]))
                    out.append((p, p[-1]))
            return out

        progress = True
        while len(F) < T and progress:
            progress = False
            cand = []
            for of in fragments:
                for mcli in of:
                    cand.append(("frag", of, mcli))
            for p, mcli in surplus_edges():
                cand.append(("surplus", p, mcli))
            cand.sort(key=lambda x: (_frag_distance(F, x[2]),
                                     0 if x[0] == "frag" else 1))
            for kind2, src, mcli in cand:
                if len(F) >= T or len(F) + 1 > M:
                    break
                src.remove(mcli)
                F.append(mcli)
                progress = True
                if kind2 == "frag" and not src:
                    fragments.remove(src)
                break                                # re-rank after each move

        if len(F) >= T:
            pools.append(F)
            res.notes.append(f"fragment completed via donors -> {_ids(F)}")
            continue

        if allow_dissolve:
            leftover = []
            for c in sorted(F, key=lambda c: c.pos):
                target = min((p for p in pools if len(p) < M),
                             key=lambda p: _frag_distance(p, c), default=None)
                if target is not None:
                    target.append(c)
                else:
                    leftover.append(c)
            if leftover:
                res.defects.append(_ids(leftover))
                res.notes.append(f"dissolve: {_ids(leftover)} unplaceable -> defect")
            else:
                res.notes.append("dissolve: fragment fully salvaged")
        else:
            res.defects.append(_ids(F))
            res.notes.append(f"defect: {_ids(F)} stranded "
                             f"(allowDissolve=false)")

    res.pools = [_ids(p) for p in pools]
    return res


def _ids(client_list):
    return [c.cid for c in client_list]
