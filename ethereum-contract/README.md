# Ethereum Anchoring Contract

Foundry project for the analytics-chain anchoring component of the supply-chain prototype.

## Layout

```text
src/SupplyChainAnchoring.sol      Cross-chain Merkle-root anchoring contract
test/SupplyChainAnchoring.t.sol   Foundry tests for anchoring behavior
lib/forge-std/                    Vendored Foundry test helpers
```

## Commands

```bash
forge build
forge test --gas-report
```

The contract stores one reconciliation record per Merkle root and rejects duplicate roots, empty roots, empty event windows, and invalid block ranges.

## Scenario Parameters

The paper scenario anchors one 1,152-event reconciliation window from the Substrate operational chain. The current Foundry gas report is:

- `anchorReconciliation`: 275,446 gas
- Cost at 0.5 gwei and $2,000 ETH: about $0.28 per anchoring
