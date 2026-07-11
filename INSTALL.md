# Installation Guide

## Prerequisites

- Python 3.8+
- Rust 1.70+ (optional, for Substrate pallet)
- Foundry (optional, for Ethereum contract)

## Setup

### 1. Clone Repository

```bash
git clone [your-repo-url]
cd multichain-prototype
```

### 2. Install Python Dependencies

```bash
cd workload-generator
pip install -r requirements.txt
```

### 3. (Optional) Install Foundry

For Ethereum contract testing:

```bash
curl -L https://foundry.paradigm.xyz | bash
foundryup
```

### 4. (Optional) Install Rust

For Substrate pallet compilation:

```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
```

## Running Experiments

### Generate Workload

```bash
make workload
```

Or manually:
```bash
cd workload-generator
python3 generate_scenario.py
```

Optional generator controls:
```bash
python3 generate_scenario.py --seed 1152 --start-time 1700000000 --output agricultural_scenario_1152_events.json
```

### Test Ethereum Contract

```bash
make ethereum
```

Or manually:
```bash
cd ethereum-contract
forge test --gas-report
```

The Ethereum project uses the Foundry layout:
- `src/SupplyChainAnchoring.sol` - anchoring contract
- `test/SupplyChainAnchoring.t.sol` - gas and behavior tests
- `lib/forge-std` - vendored Foundry test helpers

## Troubleshooting

**Python module not found:**
```bash
pip install --break-system-packages pynacl
```

**Forge command not found:**
```bash
source ~/.zshenv  # or ~/.bashrc
foundryup
```

## Outputs

- `workload-generator/agricultural_scenario_1152_events.json` - Generated events
- Console output shows cost analysis and validation results
- Foundry writes Ethereum build artifacts under `ethereum-contract/out/` and `ethereum-contract/cache/`
