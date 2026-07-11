// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.20;

import "forge-std/Test.sol";
import "../src/SupplyChainAnchoring.sol";

contract SupplyChainAnchoringTest is Test {
    SupplyChainAnchoring public anchoring;
    
    function setUp() public {
        anchoring = new SupplyChainAnchoring();
    }
    
    function testAnchorReconciliation() public {
        SupplyChainAnchoring.ReconciliationPayload memory payload = SupplyChainAnchoring.ReconciliationPayload({
            merkleRoot: bytes32(uint256(0x9f2e4a7bc3d8f1e2a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8)),
            startBlock: 1000,
            endBlock: 1500,
            eventCount: 1152,
            timestamp: block.timestamp,
            chainId: "substrate-operational-01"
        });
        
        bool success = anchoring.anchorReconciliation(payload);
        
        assertTrue(success, "Anchoring should succeed");
        assertEq(anchoring.totalAnchorings(), 1, "Should have 1 anchoring");
    }
}
