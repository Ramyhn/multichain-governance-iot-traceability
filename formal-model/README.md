# Formal Model and Verification

Machine-checked model of the governed multichain protocol described in the paper
(Section 7, *System Model, Formal Analysis, and Guarantees*). The system is
modeled as a network of communicating automata — device, governance pallet,
reconciliation service, analytics/auditor, and actors — and the protocol-level
**safety** and **liveness** properties are verified by exhaustive state-space
exploration.

Cryptographic properties (measurement unforgeability, anchor tamper-evidence)
are established by the computational proofs in the paper and abstracted here as
booleans; this model checks the state-machine properties that govern *who may do
what, in what order, and whether the system makes progress*.

## Properties verified

| Property | Meaning |
|---|---|
| INV1 — governance safety | no illegal transition/measurement is ever committed |
| INV2 — tamper-evidence   | no tampered anchor is ever accepted by an auditor |
| L1 — deadlock freedom    | every non-final reachable state has a successor |
| L2 — progress            | the completed state (terminal and fully anchored) stays reachable |

## Artifacts

### `model_check.py` — explicit-state checker (no dependencies)

A self-contained Python explicit-state model checker. Runs the deployed model
plus two control experiments — governance guard removed, and auditor removed —
that show each safety property is enforced by exactly one mechanism.

```
python3 model_check.py
```

Expected output: the deployed model satisfies all four properties over its full
reachable state space (195 states); the guard-off run breaks governance safety
with a one-step counterexample, and the auditor-off run breaks tamper-evidence
with a three-step counterexample.

### `governed_multichain.xml` + `governed_multichain.q` — UPPAAL model

A network of timed automata that adds real clocks for the freshness window and
the finality/anchoring delay. Verify with UPPAAL's `verifyta`:

```
verifyta governed_multichain.xml governed_multichain.q
```

or open the `.xml` in the UPPAAL GUI and run the embedded queries from the
Verifier tab. All four queries are satisfied on the deployed model. To reproduce
the control experiments, set `GUARD_ENABLED = false` or `AUDITOR_ENABLED = false`
in the model's global declarations and re-run; the corresponding safety query
then fails with a diagnostic trace.

UPPAAL (free academic license) is available at <https://uppaal.org>.
