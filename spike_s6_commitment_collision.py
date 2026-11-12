#!/usr/bin/env python3
"""S6 — how weak is the 4-layer commitment, really?

The README used to call it "~53 bits". That is the wrong way to describe it. The
structural layers are not independent:

    L1 = sum(b_i + i)      = sum(b_i)     + n(n-1)/2
    L2 = sum(b_i*22 + i)   = 22*sum(b_i)  + n(n-1)/2
    L3 = count(odd b_i)

so L1 and L2 are both determined by the SAME quantity (the byte sum), and L3 by
the odd-byte count — all three are invariant under **permuting the payload**.
Permutation leaves the length and the multiset of bytes untouched, so:

    any two permutations of the same payload share L1, L2 and L3 exactly.

That means the entire collision resistance of the 4-layer commitment reduces to
L0 = FNV-1a-32, a 32-bit NON-cryptographic hash. So a full 4-layer collision is
just a birthday collision among permutations of one payload (~2^16 tries), not a
2^53 search.

This script measures all of it. Run:  python3 spike_s6_commitment_collision.py
"""
import itertools
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verifier as V  # noqa: E402

FAILS = []


def chk(name, cond, detail=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name} " + (f"{detail}" if detail else ""))
    if not cond:
        FAILS.append(name)


def main():
    print("S6 — 4-layer commitment: forgeability, measured")
    base = b"POD-DELIVERY-000"          # 16 bytes, all distinct-ish
    p0 = base.decode()

    # ── 1. the structural layers really are permutation-invariant ───────────
    parts = V.commit(p0).split("-")
    rng = random.Random(1234)
    same_struct = 0
    trials = 2000
    for _ in range(trials):
        perm = list(base)
        rng.shuffle(perm)
        p = bytes(perm).decode()
        q = V.commit(p).split("-")
        if q[1:] == parts[1:]:          # L1, L2, L3 identical
            same_struct += 1
    chk("L1/L2/L3 invariant under permutation", same_struct == trials,
        f"{same_struct}/{trials} permutations kept all three structural layers")
    print(f"        (L0 changes: it is the only layer that sees byte ORDER)")

    # ── 2. find a FULL 4-layer collision among permutations ─────────────────
    # Any FNV-1a-32 match between two permutations is a full commitment collision,
    # because the other three layers are automatically equal.
    seen = {}
    t0 = time.time()
    found = None
    tries = 0
    perm_buf = list(base)
    while found is None and tries < 4_000_000:
        rng.shuffle(perm_buf)
        p = bytes(perm_buf).decode()
        c = V.commit(p)
        tries += 1
        if c in seen and seen[c] != p:
            found = (seen[c], p, c)
            break
        seen[c] = p
    dt = time.time() - t0
    chk("found a FULL 4-layer collision", found is not None,
        f"{tries:,} permutations in {dt:.1f}s ({len(seen):,} distinct commitments)")

    if found:
        a, b, c = found
        print(f"        payload A = {a!r}")
        print(f"        payload B = {b!r}")
        print(f"        commitment on both = {c}")
        chk("the two payloads differ", a != b)
        chk("predicate() accepts B for A's commitment (forged)",
            V.commit(b) == V.commit(a) and V.mismatch_layers(b, V.commit(a)) == 0)

    # ── 3. cost comparison ─────────────────────────────────────────────────
    n = len(base)
    perms = len(list(itertools.permutations(range(min(n, 6)))))
    print(f"\n  structural fact: all {n}! byte orders of a {n}-byte payload share L1/L2/L3")
    print(f"  so collision cost == an FNV-1a-32 birthday: ~2^16 permutations, measured "
          f"{tries:,} ({dt:.1f}s in pure Python)")
    print("  a cryptographic hash would need ~2^128 (sha256) — this is 2^16.")

    print()
    if FAILS:
        print(f"VERDICT: PARTIAL — {FAILS}")
        return 1
    print("VERDICT: the 4-layer commitment is NOT a security primitive. Three of its "
          "four layers are invariant under permutation, so its strength collapses to "
          "32-bit FNV-1a — a full, concrete collision was found by brute force in "
          "seconds. It is retained only as a reproducible tamper-detection demo; "
          "file identity uses the sha256 kind.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
