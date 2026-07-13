#!/usr/bin/env python3
"""
Explicit-state model check of the governed multichain traceability protocol.

This is the Phase-1 in-house cross-check that mirrors the UPPAAL model we will
author for the paper. It models the relevant components as a network of
communicating automata and verifies protocol-level SAFETY and LIVENESS by
exhaustive reachability over the (bounded) product state space.

Components (automata) and the global state they act on:
  - Actors (producer, logistics, regulator): issue lifecycle operations.
  - Governance pallet: the lifecycle FSM + guard G (role + order + precondition).
  - Devices: emit measurements; a measurement is admitted only if it is
    key-valid, fresh, and from an active (non-revoked) device.
  - Reconciliation service: bundles finalized events and anchors a Merkle root.
  - Analytics / auditor: recomputes the root and accepts iff it matches.

Cryptography is abstracted (key-validity/hash-match are booleans); the
computational proofs (Track 1) justify that abstraction. Timing (freshness
window, GST, finality delay) is abstracted to logical steps here and is added
with clocks in the UPPAAL model (Track 2).

Illegal actions the adversary may attempt (mapped to the threat model):
  out-of-order op ......... malicious actor forcing an illegal transition
  wrong-role op ........... collusion (role bypass)
  invalid measurement ..... Sybil (forged key) / key compromise (revoked device)
  byzantine anchor ........ malicious relay (tampered Merkle root)

Safety (invariants, must hold in every reachable state):
  INV1  no illegal transition/measurement is ever committed   (governance safety)
  INV2  no tampered anchor is ever accepted by an auditor      (tamper-evidence)
Liveness:
  L1    deadlock freedom: every non-final reachable state has a successor
  L2    A[] E<> done: from every reachable state the completed state
        (batch terminal AND every committed event finalized+anchored) stays
        reachable  (progress / no livelock trap)
"""
from dataclasses import dataclass
from collections import deque

# lifecycle FSM: state -> (operation, next_state, authorized_role)
LIFECYCLE = {
    'Harvested': ('package', 'Packaged',  'producer'),
    'Packaged':  ('ship',    'InTransit', 'producer'),
    'InTransit': ('deliver', 'Delivered', 'logistics'),
    'Delivered': ('inspect', 'Inspected', 'regulator'),
}
FINAL = {'Inspected', 'Rejected'}
PRECOND_MEAS = {'deliver'}          # custody transfer needs a valid measurement


@dataclass(frozen=True)
class S:
    q: str                 # batch lifecycle state
    have_meas: bool        # a valid measurement has been admitted
    committed: frozenset    # events committed on the operational chain
    finalized: frozenset    # committed events that reached finality
    anchored: frozenset     # events accepted as anchored on the analytics chain
    illegal: bool          # STICKY safety flag: an illegal event was committed
    badanchor: bool        # STICKY safety flag: a tampered anchor was accepted


def initial():
    return S('Harvested', False, frozenset(), frozenset(), frozenset(), False, False)


def is_done(s):
    return s.q in FINAL and bool(s.committed) and s.anchored == s.committed


def successors(s, guard_on, auditor_on):
    out = []
    # 1. honest lifecycle operation (correct order, role, precondition)
    if s.q in LIFECYCLE:
        op, nq, _role = LIFECYCLE[s.q]
        if op not in PRECOND_MEAS or s.have_meas:
            out.append((f'honest:{op}',
                        S(nq, s.have_meas, s.committed | {op}, s.finalized,
                          s.anchored, s.illegal, s.badanchor)))
    # 2. honest early reject (regulator terminates the batch)
    if s.q not in FINAL:
        out.append(('honest:reject',
                    S('Rejected', s.have_meas, s.committed | {'reject'}, s.finalized,
                      s.anchored, s.illegal, s.badanchor)))
    # 3. honest valid measurement (key-valid, fresh, active device)
    if s.q not in FINAL and not s.have_meas:
        out.append(('honest:measure',
                    S(s.q, True, s.committed | {'meas'}, s.finalized,
                      s.anchored, s.illegal, s.badanchor)))
    # 4a. ADVERSARY: out-of-order operation (source state != current state)
    if s.q not in FINAL:
        for src, (op, nq, _r) in LIFECYCLE.items():
            if src != s.q:
                if guard_on:
                    pass                      # guard: transition undefined -> rejected
                else:
                    out.append((f'ADV-out-of-order:{op}',
                                S(nq, s.have_meas, s.committed | {op}, s.finalized,
                                  s.anchored, True, s.badanchor)))
    # 4b. ADVERSARY: wrong-role actor performs the (order-correct) operation
    if s.q in LIFECYCLE:
        op, nq, _role = LIFECYCLE[s.q]
        if op not in PRECOND_MEAS or s.have_meas:
            if guard_on:
                pass                          # guard: role check fails -> rejected
            else:
                out.append((f'ADV-wrong-role:{op}',
                            S(nq, s.have_meas, s.committed | {op}, s.finalized,
                              s.anchored, True, s.badanchor)))
    # 4c. ADVERSARY: custody transfer with the precondition unmet (no measurement)
    if s.q == 'InTransit' and not s.have_meas:
        if guard_on:
            pass                              # guard: precondition fails -> rejected
        else:
            out.append(('ADV-missing-precond:deliver',
                        S('Delivered', s.have_meas, s.committed | {'deliver'},
                          s.finalized, s.anchored, True, s.badanchor)))
    # 5. ADVERSARY: invalid measurement (forged key / revoked-or-suspended device)
    if s.q not in FINAL and not s.have_meas:
        if guard_on:
            pass                              # guard: device/sig check fails -> rejected
        else:
            out.append(('ADV-invalid-measure',
                        S(s.q, True, s.committed | {'meas'}, s.finalized,
                          s.anchored, True, s.badanchor)))
    # 6. finality: committed events reach finality (enables anchoring)
    if s.committed - s.finalized:
        out.append(('finalize',
                    S(s.q, s.have_meas, s.committed, frozenset(s.committed),
                      s.anchored, s.illegal, s.badanchor)))
    # 7. honest anchor: reconciler anchors the true finalized set; auditor accepts
    if s.finalized and s.anchored != s.finalized:
        out.append(('honest-anchor',
                    S(s.q, s.have_meas, s.committed, s.finalized,
                      frozenset(s.finalized), s.illegal, s.badanchor)))
    # 8. ADVERSARY: byzantine anchor of a tampered set (drop one finalized event)
    if len(s.finalized) >= 1 and s.anchored != s.finalized:
        tampered = frozenset(sorted(s.finalized)[1:])   # drop the smallest element
        if auditor_on:
            pass                              # auditor recomputes -> mismatch -> flagged
        else:
            out.append(('ADV-byzantine-anchor',
                        S(s.q, s.have_meas, s.committed, s.finalized,
                          tampered, s.illegal, True)))
    return out


def explore(guard_on, auditor_on):
    """BFS the reachable state space; return states, edges, predecessors."""
    init = initial()
    seen = {init}
    pred = {init: (None, None)}        # state -> (parent, action)
    edges = 0
    dq = deque([init])
    while dq:
        s = dq.popleft()
        for label, ns in successors(s, guard_on, auditor_on):
            edges += 1
            if ns not in seen:
                seen.add(ns)
                pred[ns] = (s, label)
                dq.append(ns)
    return init, seen, pred, edges


def path_to(pred, target):
    seq = []
    s = target
    while s is not None:
        parent, action = pred[s]
        if action is not None:
            seq.append(action)
        s = parent
    return list(reversed(seq))


def can_reach_done(states, guard_on, auditor_on):
    """Backward reachability from done states over the reachable graph."""
    succ = {s: [ns for _, ns in successors(s, guard_on, auditor_on)] for s in states}
    rev = {s: [] for s in states}
    for s, nss in succ.items():
        for ns in nss:
            if ns in rev:
                rev[ns].append(s)
    good = {s for s in states if is_done(s)}
    dq = deque(good)
    while dq:
        s = dq.popleft()
        for p in rev[s]:
            if p not in good:
                good.add(p)
                dq.append(p)
    return good, succ


def check(name, guard_on, auditor_on, expect_safe):
    init, states, pred, edges = explore(guard_on, auditor_on)
    inv1 = [s for s in states if s.illegal]
    inv2 = [s for s in states if s.badanchor]
    good, succ = can_reach_done(states, guard_on, auditor_on)
    deadlocks = [s for s in states if not is_done(s) and not succ[s]]
    livelocks = [s for s in states if s not in good]
    print(f"\n=== {name} ===")
    print(f"  reachable states: {len(states)}   transitions: {edges}")
    print(f"  INV1 no-illegal-committed : {'HOLDS' if not inv1 else 'VIOLATED'}"
          + (f"  ({len(inv1)} bad states)" if inv1 else ""))
    print(f"  INV2 no-bad-anchor        : {'HOLDS' if not inv2 else 'VIOLATED'}"
          + (f"  ({len(inv2)} bad states)" if inv2 else ""))
    print(f"  L1 deadlock-free          : {'HOLDS' if not deadlocks else f'VIOLATED ({len(deadlocks)})'}")
    print(f"  L2 done-reachable (A[]E<>): {'HOLDS' if not livelocks else f'VIOLATED ({len(livelocks)})'}")
    if inv1:
        cx = min((path_to(pred, s) for s in inv1), key=len)
        print(f"  counterexample to INV1 (shortest, {len(cx)} steps):")
        print("    " + "  ->  ".join(cx))
    if inv2:
        cx = min((path_to(pred, s) for s in inv2), key=len)
        print(f"  counterexample to INV2 (shortest, {len(cx)} steps):")
        print("    " + "  ->  ".join(cx))
    safe = not inv1 and not inv2 and not deadlocks and not livelocks
    matched = (safe == expect_safe)
    verdict = "as expected" if matched else "!!! UNEXPECTED !!!"
    print(f"  overall: {'ALL PROPERTIES HOLD' if safe else 'PROPERTY VIOLATION(S)'}  ({verdict})")
    return matched


if __name__ == '__main__':
    print("Explicit-state verification of the governed multichain protocol")
    ok = True
    # correct system: guard and auditor enabled -> everything should hold
    ok &= check("MODEL (guard ON, auditor ON)  -- the deployed protocol",
                guard_on=True, auditor_on=True, expect_safe=True)
    # sanity checks: the guard/auditor are what enforce the safety properties
    ok &= check("SANITY (guard OFF)  -- governance guard removed",
                guard_on=False, auditor_on=True, expect_safe=False)
    ok &= check("SANITY (auditor OFF)  -- auditor recomputation removed",
                guard_on=True, auditor_on=False, expect_safe=False)
    print("\n" + ("EVERY RUN MATCHED EXPECTATION." if ok
                  else "A RUN DID NOT MATCH EXPECTATION -- investigate."))
