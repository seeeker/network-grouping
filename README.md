# Network topology & client-pool grouping

Design spec and reference implementation for a daisy-chained network topology
(RCD → ADD → CHD → CLD) with client data-redundancy pooling.

## Contents

| File | Purpose |
|------|---------|
| **`SPEC.md`** | The complete specification in one file: topology rules, data/redundancy model, priority stack, grouping algorithm (census → virtual chain → flexible k, with donor/dissolve fallback), worked examples, agent-ready implementation spec with ground-truth cases, full test scenario matrix, edge-case checklist, and mirror-mode extension notes. |
| `phase1-column-pooling-flow.svg` / `phase2-fragment-completion-flow.svg` | Decision-flow diagrams embedded by the spec. |
| `grouping.py` | Reference implementation of the grouping algorithm. |
| `test_grouping.py` | Scenario suite — 96 assertions across 11 categories (A–K, incl. shard assignment). |

## Running the tests

```bash
python3 test_grouping.py
# PASS: 96 / FAIL: 0
```

No dependencies beyond the Python 3 standard library.

## Key concepts

- **T (Target Pool Size)** — minimum clients whose shards reconstruct the full data set.
- **M (Max Pool Size)** — hard cap per client type.
- Every client must land in a complete pool (`T ≤ size ≤ M`) so the data set
  survives a root (RCD) outage; `allowDissolve` controls what happens when a
  fragment cannot be completed.

Open design decisions are marked inline in `SPEC.md` (pool immutability, CLD
daisy-chain positions, seam-size trade, multi-deficient pairing order).
