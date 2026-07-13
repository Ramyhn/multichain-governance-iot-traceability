// Safety and liveness queries for governed_multichain.xml
//
// Command-line:   verifyta governed_multichain.xml governed_multichain.q
// GUI:            open the .xml, go to the Verifier tab, run each query below.
//
// Expected on the deployed model (GUARD_ENABLED = AUDITOR_ENABLED = true): all satisfied.
// To reproduce the controls, set GUARD_ENABLED=false (INV1 fails) or
// AUDITOR_ENABLED=false (INV2 fails) in the model's global declarations and re-run.

A[] not illegal      // INV1  governance safety: no illegal transition/measurement is ever committed
A[] not badanchor    // INV2  tamper-evidence: no tampered anchor is ever accepted
A[] not deadlock     // L1    deadlock freedom
E<> done()           // L2    progress: the completed (terminal + fully anchored) state is reachable
