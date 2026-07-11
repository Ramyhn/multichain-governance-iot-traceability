# Multichain Supply Chain Prototype

Experimental implementation of the multichain architecture described in "A Governance-Enforced Multichain Architecture for Verifiable IoT-Based Supply Chain Traceability" (El Gharbawy and Barati).

## Repository Structure

```
├── substrate-pallet/       # Operational chain (FRAME pallet, Rust)
├── ethereum-contract/      # Analytics chain anchoring (Solidity)
├── workload-generator/     # Synthetic event generation (Python)
├── analysis/               # Result processing (Python)
├── simulation/             # Deployment-robustness study (Python)
├── runtime/                # Substrate runtime for weight benchmarking
├── results/                # Measured pallet weights
└── README.md               # This file
```

## Components

### Substrate Pallet

Implements Algorithms 1-3 from the paper:
- Device onboarding with Ed25519 signatures
- IoT event processing with replay attack prevention
- Governance evaluation with finite state machine

**File:** `substrate-pallet/lib.rs` (443 lines)
**Language:** Rust (FRAME)
**Requirements:** Substrate 3.0+

### Ethereum Contract

Implements Algorithm 4:
- Cross-chain Merkle root anchoring
- Verification functions for audit
- Access control

**File:** `ethereum-contract/src/SupplyChainAnchoring.sol` (250 lines)
**Language:** Solidity 0.8.20
**Gas:** 275,446 gas per anchoring

### Workload Generator

Generates agricultural scenario from paper Section VII:
- 5 Ed25519-signed IoT devices
- 1,152 sensor events (temperature, humidity, GPS)
- 2 custody-transfer records
- Merkle tree construction
- Cost analysis

**File:** `workload-generator/generate_scenario.py` (452 lines)
**Language:** Python 3.8+

## Quick Start

### Generate Workload (5 minutes)

```bash
cd workload-generator
pip install -r requirements.txt
python3 generate_scenario.py
```

Output: `agricultural_scenario_1152_events.json`

The generator is deterministic by default. Use `--seed`, `--start-time`, or `--output` to produce a different run.

### Measure Ethereum Gas (15 minutes)

```bash
cd ethereum-contract
forge install foundry-rs/forge-std
forge build
forge test --gas-report
```

Expected gas report: 275,446 gas for `anchorReconciliation`

## Experimental Results

| Metric | Value |
|--------|-------|
| Events generated | 1,152 |
| Devices | 5 |
| Gas consumption | 275,446 |
| Cost per batch (25 gwei, $2,000 ETH) | $13.78 |
| Cost per event | $0.012 |

## Validation

This implementation validates:
1. Algorithmic correctness (Ed25519 signatures, Merkle trees)
2. Gas consumption claims from paper
3. Computational complexity (O(n log n) for Merkle construction)
4. Event schema and structure

## Limitations

- Local EVM measurements (not testnet/mainnet)
- Synthetic workload (not real sensors)
- Limited scale (5 devices, 1,152 events)
- No penetration testing

## Robustness Simulation

`simulation/robustness_simulation.py` reproduces the deployment-robustness study: network partition, validator churn, intermittent device connectivity, and IPFS availability. It writes four PDF figures and a summary CSV.

```bash
pip install numpy matplotlib
python3 simulation/robustness_simulation.py OUTPUT_DIR
```

## Citation

If you use this code, please cite:

R. El Gharbawy and M. Barati, "A Governance-Enforced Multichain Architecture for Verifiable IoT-Based Supply Chain Traceability," 2026.

## License

Apache 2.0

