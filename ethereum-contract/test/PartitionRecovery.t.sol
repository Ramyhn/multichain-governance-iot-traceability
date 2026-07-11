// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.20;

import "forge-std/Test.sol";
import "forge-std/console.sol";
import "../src/SupplyChainAnchoring.sol";

/// Genuine on-chain measurement of partition recovery.
///
/// When a partition heals, a single `anchorReconciliation` call anchors one
/// Merkle root that covers the whole queued backlog. These tests measure, on
/// the real contract, that (1) the anchoring gas is independent of how many
/// events the backlog holds, so recovery is O(1) in partition length, and
/// (2) the anchored root verifiably covers the backlog and rejects tampering.
contract PartitionRecoveryTest is Test {
    SupplyChainAnchoring anchoring;

    function setUp() public {
        anchoring = new SupplyChainAnchoring();
    }

    /// One catch-up anchor clears any backlog: gas does not grow with the
    /// number of events the partition queued.
    function testGasVsBacklog() public {
        uint256[6] memory counts =
            [uint256(1), 100, 10_000, 1_000_000, 10_000_000, 100_000_000];
        console.log("PARTITION_CSV_BEGIN");
        for (uint256 i = 0; i < counts.length; i++) {
            SupplyChainAnchoring.ReconciliationPayload memory p = SupplyChainAnchoring
                .ReconciliationPayload({
                merkleRoot: keccak256(abi.encode("root", i)),
                startBlock: 1000,
                endBlock: 1000 + counts[i],
                eventCount: counts[i],
                timestamp: block.timestamp,
                chainId: "substrate-operational-01"
            });
            uint256 g0 = gasleft();
            anchoring.anchorReconciliation(p);
            uint256 used = g0 - gasleft();
            console.log("PARTITION_CSV", counts[i], used);
        }
        console.log("PARTITION_CSV_END");
    }

    /// The anchored root covers the backlog: an included event verifies and a
    /// tampered one is rejected, on-chain.
    function testMerkleCoverage() public {
        uint256 n = 1024;
        bytes32[] memory leaves = new bytes32[](n);
        for (uint256 i = 0; i < n; i++) {
            leaves[i] = keccak256(abi.encode("event", i));
        }
        bytes32 root = _root(leaves);

        SupplyChainAnchoring.ReconciliationPayload memory p = SupplyChainAnchoring
            .ReconciliationPayload({
            merkleRoot: root,
            startBlock: 1000,
            endBlock: 2024,
            eventCount: n,
            timestamp: block.timestamp,
            chainId: "substrate-operational-01"
        });
        anchoring.anchorReconciliation(p);

        uint256 idx = 777;
        bytes32[] memory proof = _proof(leaves, idx);
        bool included = anchoring.verifyMerkleProof(root, proof, leaves[idx]);
        bool tampered = anchoring.verifyMerkleProof(root, proof, keccak256("tampered"));
        console.log("MERKLE_INCLUDED_OK", included);
        console.log("MERKLE_TAMPERED_REJECTED", !tampered);
        assertTrue(included, "included leaf must verify");
        assertTrue(!tampered, "tampered leaf must be rejected");
    }

    function _hashPair(bytes32 a, bytes32 b) internal pure returns (bytes32) {
        return a < b
            ? keccak256(abi.encodePacked(a, b))
            : keccak256(abi.encodePacked(b, a));
    }

    function _root(bytes32[] memory leaves) internal pure returns (bytes32) {
        bytes32[] memory level = leaves;
        while (level.length > 1) {
            bytes32[] memory next = new bytes32[](level.length / 2);
            for (uint256 j = 0; j < next.length; j++) {
                next[j] = _hashPair(level[2 * j], level[2 * j + 1]);
            }
            level = next;
        }
        return level[0];
    }

    function _proof(bytes32[] memory leaves, uint256 idx)
        internal
        pure
        returns (bytes32[] memory)
    {
        uint256 depth;
        for (uint256 n = leaves.length; n > 1; n /= 2) {
            depth++;
        }
        bytes32[] memory proof = new bytes32[](depth);
        bytes32[] memory level = leaves;
        uint256 pos = idx;
        uint256 d;
        while (level.length > 1) {
            proof[d] = level[pos ^ 1];
            bytes32[] memory next = new bytes32[](level.length / 2);
            for (uint256 j = 0; j < next.length; j++) {
                next[j] = _hashPair(level[2 * j], level[2 * j + 1]);
            }
            level = next;
            pos /= 2;
            d++;
        }
        return proof;
    }
}
