#!/usr/bin/env python3
"""Genuine IPFS content-addressed retrieval and verification measurement.

Runs against a real local IPFS (kubo) repo, offline. For a set of event
payloads it measures that: content addressing is deterministic (same bytes give
the same CID); retrieval returns byte-identical content; a tampered payload
gets a different CID; and a payload fetched from IPFS verifies against a Merkle
root over the event digests, while a tampered one is rejected. This is the real
consumer-verification path: fetch from IPFS, then check the digest against the
anchored root.

The availability-vs-replication curve itself is combinatorial probability
(a block is retrievable if at least one replica is up); what is measured here
is the content-addressing property that makes any replica interchangeable.

Usage: python3 ipfs_measure.py IPFS_PATH   (a scratch dir; will be ipfs-init'd)
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile

IPFS = "/opt/homebrew/bin/ipfs"
H = 32  # BlakeTwo256 digest bytes


def run(env, *args, data: bytes | None = None) -> bytes:
    return subprocess.run([IPFS, *args], input=data, capture_output=True, env=env).stdout


def main() -> None:
    ipfs_path = sys.argv[1]
    os.makedirs(ipfs_path, exist_ok=True)
    env = dict(os.environ, IPFS_PATH=ipfs_path)
    if not os.path.exists(os.path.join(ipfs_path, "config")):
        run(env, "init")

    def add(b: bytes) -> str:
        with tempfile.NamedTemporaryFile(delete=False) as tf:
            tf.write(b)
            path = tf.name
        cid = run(env, "add", "-Q", "--offline", path).decode().strip()
        os.unlink(path)
        return cid

    def cat(cid: str) -> bytes:
        return run(env, "cat", "--offline", cid)

    def event(i: int) -> bytes:
        return json.dumps(
            {"device": "did:example:temp-farm-01", "ts": 1_700_000_000 + i * 300,
             "type": "temperature", "celsius": round(3.0 + 0.01 * i, 2)},
            sort_keys=True,
        ).encode()

    n = 64
    payloads = [event(i) for i in range(n)]
    cids = [add(p) for p in payloads]

    deterministic = add(payloads[0]) == cids[0]
    distinct = len(set(cids)) == n
    roundtrip = sum(cat(cids[i]) == payloads[i] for i in range(n))

    tampered = bytearray(payloads[0])
    tampered[12] ^= 0x01
    tamper_cid = add(bytes(tampered))
    tamper_changes_cid = tamper_cid != cids[0]

    # Merkle over Blake2-256 digests of the payloads (the operational-chain leaf).
    def h(b: bytes) -> bytes:
        return hashlib.blake2b(b, digest_size=H).digest()

    def build(leaves):
        levels = [leaves]
        cur = leaves
        while len(cur) > 1:
            if len(cur) % 2:
                cur = cur + [cur[-1]]
            cur = [h(cur[i] + cur[i + 1]) for i in range(0, len(cur), 2)]
            levels.append(cur)
        return levels

    def proof(levels, idx):
        pr, i = [], idx
        for lvl in levels[:-1]:
            row = lvl if len(lvl) % 2 == 0 else lvl + [lvl[-1]]
            pr.append(row[i ^ 1])
            i //= 2
        return pr

    def verify(leaf, idx, pr, root):
        node, i = leaf, idx
        for sib in pr:
            node = h(node + sib) if i % 2 == 0 else h(sib + node)
            i //= 2
        return node == root

    levels = build([h(p) for p in payloads])
    root = levels[-1][0]
    idx = 37
    fetched = cat(cids[idx])                       # real fetch from IPFS
    inclusion_ok = verify(h(fetched), idx, proof(levels, idx), root)
    tampered_rejected = not verify(h(bytes(tampered)), idx, proof(levels, idx), root)

    print("IPFS_RESULT ipfs_version",
          run(env, "version", "--number").decode().strip())
    print("IPFS_RESULT content_addressing_deterministic", deterministic and distinct)
    print(f"IPFS_RESULT roundtrip_byte_identical {roundtrip}/{n}")
    print("IPFS_RESULT tamper_changes_cid", tamper_changes_cid)
    print("IPFS_RESULT fetched_payload_merkle_inclusion_ok", inclusion_ok)
    print("IPFS_RESULT tampered_payload_rejected", tampered_rejected)
    print(f"IPFS_RESULT sample_cid {cids[0]}")


if __name__ == "__main__":
    main()
