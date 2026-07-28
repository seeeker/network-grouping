# Network topology & client-pool grouping

Design spec and reference implementation for a daisy-chained network topology
(RCD → ADD → CHD → CLD) with client data-redundancy pooling.

## Contents

| File | Purpose |
|------|---------|
| `network-topology-reference.md` | The spec: topology rules, data/redundancy model, priority stack, grouping algorithm (census → virtual chain → flexible k, with donor/dissolve fallback), worked examples, edge-case test checklist, mirror-mode extension notes. |
| `phase1-column-pooling-flow.svg` / `phase2-fragment-completion-flow.svg` | Decision-flow diagrams embedded by the spec. |
| `grouping.py` | Reference implementation of the grouping algorithm. |
| `test_grouping.py` | Scenario suite — 84 assertions across 10 categories (A–J). |
| `grouping-test-scenarios.md` | Human-readable scenario matrix with expected outcomes. |
| `IMPLEMENTATION-SPEC.md` | Self-contained spec for implementing the algorithm from scratch (agent-ready): model, math, phases, priority stack, open forks, ground-truth verification cases. |

## Running the tests

```bash
python3 test_grouping.py
# PASS: 84 / FAIL: 0
```

No dependencies beyond the Python 3 standard library.

## Key concepts

- **T (Target Pool Size)** — minimum clients whose shards reconstruct the full data set.
- **M (Max Pool Size)** — hard cap per client type.
- Every client must land in a complete pool (`T ≤ size ≤ M`) so the data set
  survives a root (RCD) outage; `allowDissolve` controls what happens when a
  fragment cannot be completed.

Open design decisions are marked inline in the spec (pool immutability, CLD
daisy-chain positions, seam-size trade, multi-deficient pairing order).
