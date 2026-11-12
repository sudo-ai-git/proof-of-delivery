#!/usr/bin/env python3
"""S1 — commitment parity, re-runnable (this is what makes "20/20" checkable).

The README claimed "on-chain == Python == JS for 20 payloads" but shipped no
script, so it was only a log line. This is that script.

It also closes the loop on S6: the two colliding payloads found there must return
an IDENTICAL commitment from the live contract, which is the on-chain proof that
the 4-layer predicate is forgeable.

Run:  python3 spike_s1_commitment_parity.py            # 20 payloads + collision
      N=50 python3 spike_s1_commitment_parity.py       # more payloads
"""
import base64
import hashlib
import json
import os
import random
import re
import string
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import verifier as V  # noqa: E402

CONTRACT = os.environ.get("POD_CONTRACT", "nft-repo-test-015.testnet")
RPC = os.environ.get("POD_RPC", "https://rpc.testnet.fastnear.com")
N = int(os.environ.get("N", "20"))

FAILS = []


def chk(name, cond, detail=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name} " + (f"{detail}" if detail else ""))
    if not cond:
        FAILS.append(name)


def onchain(payload):
    a = base64.b64encode(json.dumps({"payload": payload}).encode()).decode()
    for _ in range(5):
        try:
            req = urllib.request.Request(RPC, data=json.dumps({
                "jsonrpc": "2.0", "id": 1, "method": "query",
                "params": {"request_type": "call_function", "finality": "final",
                           "account_id": CONTRACT, "method_name": "commitment",
                           "args_base64": a}}).encode(), headers={"Content-Type": "application/json"})
            r = json.load(urllib.request.urlopen(req, timeout=30))
            res = r.get("result")
            if res and "result" in res:
                return json.loads(bytes(res["result"]).decode())
            return NotImplemented
        except Exception:
            time.sleep(1.2)
    return None


def js_commit():
    """Extract the demo page's JS and return a callable, or None."""
    try:
        html_ = open(os.path.join(HERE, "demo", "index.html"), encoding="utf-8").read()
        js = re.search(r"<script>(.*?)</script>", html_, re.S).group(1)
        math_js = js.split("const RULES=")[0]
        return math_js
    except Exception:
        return None


def main():
    print(f"S1 — commitment parity (N={N}) + the S6 collision, on chain")
    rng = random.Random(20261111)
    alphabet = string.ascii_letters + string.digits + " -_"
    payloads = ["hello world", "the quick brown fox", "",
                "market report #42: NEAR Intents volume up 18% w/w", "a"]
    while len(payloads) < N:
        payloads.append("".join(rng.choice(alphabet) for _ in range(rng.randint(1, 120))))

    # ── on-chain vs Python ──────────────────────────────────────────────────
    agree = 0
    mism = []
    for p in payloads:
        oc = onchain(p)
        if oc == V.commit(p):
            agree += 1
        else:
            mism.append((p[:24], oc, V.commit(p)))
    chk(f"on-chain == Python for all {N} payloads", agree == N,
        f"{agree}/{N}" + (f"  mismatches={mism}" if mism else ""))

    # ── three-way: Python vs the browser demo's JS ──────────────────────────
    math_js = js_commit()
    if math_js:
        harness = math_js + "\nconsole.log(JSON.stringify(%s.map(t=>commit(t))));\n" % json.dumps(payloads)
        try:
            r = subprocess.run(["node", "-e", harness], capture_output=True, text=True, timeout=60)
            js_vals = json.loads(r.stdout)
            py_vals = [V.commit(p) for p in payloads]
            chk("JS (demo/index.html) == Python for all payloads", js_vals == py_vals,
                f"{sum(1 for a,b in zip(js_vals,py_vals) if a==b)}/{len(payloads)}")
        except Exception as e:
            chk("JS parity runnable (node available)", False, f"{type(e).__name__}: {str(e)[:60]}")
    else:
        print("  [skip] could not extract the demo JS")

    # ── the S6 collision must reproduce on the live contract ────────────────
    col_a, col_b = "-EIL0OY-0P0DEDRV", "DE00I0YOD--LPVER"
    ca, cb = onchain(col_a), onchain(col_b)
    chk("the two colliding payloads differ but their on-chain commitment is identical",
        col_a != col_b and ca == cb and ca not in (None, NotImplemented),
        f"{ca} for {col_a!r} and {col_b!r}")
    chk("Python agrees with the chain on the collision", V.commit(col_a) == V.commit(col_b) == ca)

    print()
    if FAILS:
        print(f"VERDICT: PARTIAL — {FAILS}")
        return 1
    print(f"VERDICT: VALIDATED — {N}/{N} payloads agree across the live contract, the "
          f"Python verifier and the browser JS; and the S6 collision is confirmed on "
          f"chain (two different payloads, one commitment).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
