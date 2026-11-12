#!/usr/bin/env python3
"""Independent Python reference for the Proof-of-Delivery commitment.

Mirrors assembly/index.ts EXACTLY (ASCII payloads; input is charCodeAt & 0xff).
If the contract and this file disagree on any payload, the contract is wrong —
this is the cross-environment determinism gate the AI judge must also pass.
"""
FNV_OFFSET = 2166136261
FNV_PRIME = 16777619


def fnv1a(s: str) -> int:
    h = FNV_OFFSET
    for ch in s:
        h = ((h ^ (ord(ch) & 0xFF)) * FNV_PRIME) & 0xFFFFFFFF
    return h


def sum_gate(s: str) -> int:
    acc = 0
    for i, ch in enumerate(s):
        acc += (ord(ch) & 0xFF) + i
    return acc % 231


def lin_gate(s: str) -> int:
    acc = 0
    for i, ch in enumerate(s):
        acc += (ord(ch) & 0xFF) * 22 + i
    return acc % 231


def odd_gate(s: str) -> int:
    c = 0
    for ch in s:
        if (ord(ch) & 0xFF) & 1:
            c += 1
    return c % 37


def commit(s: str) -> str:
    return f"{fnv1a(s):08x}-{sum_gate(s):02x}-{lin_gate(s):02x}-{odd_gate(s):02x}"


def broken_mask(payload: str, expected: str) -> int:
    parts = expected.split("-")
    if len(parts) != 4:
        return 15
    mask = 0
    if f"{fnv1a(payload):08x}" != parts[0]:
        mask |= 1
    if f"{sum_gate(payload):02x}" != parts[1]:
        mask |= 2
    if f"{lin_gate(payload):02x}" != parts[2]:
        mask |= 4
    if f"{odd_gate(payload):02x}" != parts[3]:
        mask |= 8
    return mask


def mismatch_layers(payload: str, expected: str) -> int:
    return bin(broken_mask(payload, expected)).count("1")


if __name__ == "__main__":
    import sys
    for p in sys.argv[1:] or ["hello world"]:
        print(p, "->", commit(p))
