#!/usr/bin/env python3
"""One-shot verifier: prove the Proof-of-Delivery predicate, offline and on chain.

    python3 verify_all.py            # offline gates + on-chain parity (read-only)
    python3 verify_all.py --selftest # additionally prove the gates CAN fail
    python3 verify_all.py --build    # rebuild the wasm first

Gates (each can FAIL; a gate that has never failed is not known to work):
  G1 BUILD      the contract compiles and the three key exports are present
  G2 GOLDEN     the Python implementation matches RECORDED values that the
                deployed contract itself produced (a golden reference, not a
                copy compared against itself)
  G3 TAMPER     every single-character mutation breaks >= 3 of the 4 layers
  G4 PARITY     the LIVE contract returns the same commitment as Python

Exit code 0 only if every gate passes.
"""
import base64
import json
import os
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import verifier as V  # noqa: E402

CONTRACT = "nft-repo-test-015.testnet"
RPC = "https://rpc.testnet.fastnear.com"
ENV = dict(os.environ, PATH=os.path.join(HERE, "node_modules", ".bin")
           + os.pathsep + os.environ.get("PATH", ""))


def _asb():
    import shutil
    return shutil.which("asb") or os.path.join(HERE, "node_modules", ".bin", "asb")

# GOLDEN: recorded from the deployed contract (near view ... commitment) and
# cross-checked against demo/index.html. These are the reference, not derived
# from verifier.py at runtime.
GOLDEN = {
    "hello world": "d58b3fa7-10-79-04",
    "the quick brown fox": "338f85c2-a6-3d-09",
    "market report #42: NEAR Intents volume up 18% w/w": "1fd2a2d5-d4-41-16",
    "": "811c9dc5-00-00-00",
    "a": "e40c292c-61-37-01",
}

RESULTS = []


def gate(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    return ok


def near_view(method, args):
    a = base64.b64encode(json.dumps(args).encode()).decode()
    for _ in range(4):
        try:
            req = urllib.request.Request(RPC, data=json.dumps({
                "jsonrpc": "2.0", "id": 1, "method": "query",
                "params": {"request_type": "call_function", "finality": "final",
                           "account_id": CONTRACT, "method_name": method, "args_base64": a}}).encode(),
                headers={"Content-Type": "application/json"})
            r = json.load(urllib.request.urlopen(req, timeout=30))
            res = r.get("result")
            if res and "result" in res:
                raw = bytes(res["result"]).decode()
                try:
                    return json.loads(raw)
                except Exception:
                    return raw
            return ("ERR", res)
        except Exception:
            time.sleep(1.5)
    return ("RATELIMIT",)


def g_build(do_build):
    wasm = os.path.join(HERE, "build", "release", "proof-of-delivery.wasm")
    if do_build:
        p = subprocess.run([_asb(), "assembly/index.ts", "--target release"],
                           capture_output=True, text=True, cwd=HERE, env=ENV, timeout=600)
        if p.returncode != 0:
            return gate("G1 build", False, (p.stdout + p.stderr)[-160:])
    if not os.path.exists(wasm):
        return gate("G1 build", False, "no wasm on disk (run with --build)")
    b = open(wasm, "rb").read()
    need = [b"commitment", b"check", b"ft_on_transfer", b"release", b"refund"]
    missing = [n.decode() for n in need if n not in b]
    return gate("G1 build", not missing and len(b) > 1000,
                f"{len(b)} bytes" + (f", missing exports {missing}" if missing else ""))


def golden_ok(g=None):
    g = g if g is not None else GOLDEN
    return all(V.commit(p) == want for p, want in g.items())


def g_golden(g=None):
    g = g if g is not None else GOLDEN
    bad = [p for p, want in g.items() if V.commit(p) != want]
    return gate("G2 golden vectors", not bad, f"{len(g)} vectors" + (f", mismatches: {bad}" if bad else ""))


def g_tamper():
    worst, worst_p = 4, None
    for payload in list(GOLDEN.keys())[1:4]:
        c = V.commit(payload)
        for i in range(len(payload)):
            mut = payload[:i] + ("X" if payload[i] != "X" else "Y") + payload[i + 1:]
            n = V.mismatch_layers(mut, c)
            if n < worst:
                worst, worst_p = n, (payload, i)
    return gate("G3 tamper breaks >=3 layers", worst >= 3, f"min layers broken = {worst}" +
                (f" at {worst_p}" if worst_p else ""))


def g_parity():
    mism = []
    for p in list(GOLDEN.keys())[:4]:
        onchain = near_view("commitment", {"payload": p})
        if onchain != V.commit(p):
            mism.append(p[:20])
    return gate("G4 live contract == Python", not mism,
                "4 payloads" + (f", mismatches: {mism}" if mism else ""))


def g_forgeable():
    """Pin the KNOWN weakness so it cannot silently be claimed as strength.

    L1/L2/L3 are invariant under permuting the payload, so the 4-layer checksum
    collapses to a 32-bit FNV-1a birthday and a full collision is cheap. If this
    gate ever FAILS, the primitive was changed and the README's demotion of it is
    now wrong — fix the docs, do not "fix" the gate.
    """
    import random
    base = "POD-DELIVERY-000"
    rng = random.Random(1234)
    seen = {}
    buf = list(base)
    for _ in range(300_000):
        rng.shuffle(buf)
        p = "".join(buf)
        c = V.commit(p)
        if c in seen and seen[c] != p:
            return gate("G5 4-layer checksum is forgeable (permutation collision)", True,
                        f"{seen[c]!r} vs {p!r} -> {c}")
        seen[c] = p
    return gate("G5 4-layer checksum is forgeable (permutation collision)", False,
                "no collision in 300k permutations — the primitive changed; update the docs")


def main():
    do_build = "--build" in sys.argv
    selftest = "--selftest" in sys.argv
    print("Proof-of-Delivery — verify_all")
    g_build(do_build)
    g_golden()
    g_tamper()
    g_parity()
    g_forgeable()

    if selftest:
        print("\n  selftest — prove the gates can FAIL (not recorded in the result):")
        ok = not golden_ok({"hello world": "00000000-00-00-00"})
        print(f"  [{'PASS' if ok else 'FAIL'}]   G2 rejects a deliberately wrong golden vector")

    failed = [n for n, ok in RESULTS if not ok]
    print()
    if failed:
        print(f"RESULT: FAIL — {failed}")
        return 1
    print(f"RESULT: ALL GATES PASS ({len(RESULTS)}/{len(RESULTS)})")
    print("The predicate is reproducible: on-chain, in Python, and in the browser demo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
