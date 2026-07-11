# Multichain Supply Chain Prototype - Makefile

.PHONY: help workload ethereum clean

help:
	@echo "Available commands:"
	@echo "  make workload   - Generate synthetic event workload"
	@echo "  make ethereum   - Test Ethereum contract and measure gas"
	@echo "  make clean      - Remove generated files"

workload:
	cd workload-generator && python3 generate_scenario.py

ethereum:
	cd ethereum-contract && forge test --gas-report

clean:
	rm -f workload-generator/agricultural_scenario_1152_events.json
	rm -rf ethereum-contract/out/
	rm -rf ethereum-contract/cache/
