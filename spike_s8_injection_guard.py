#!/usr/bin/env python3
"""S8 — the predicate-injection guard.

The deal record is a hand-built JSON string, and `predicate` was free text. A
crafted predicate such as

    x","released":true,"deadline":1,"p":"

broke out of its string and injected a SECOND "deadline"/"released" before the
real ones. Because the parser returns the FIRST match for a key, the deal's
effective deadline became 1 — so after a seller delivered, the buyer could
`refund` immediately and keep the artifact. Reproduced on chain before the fix.

pod-5 restricts the predicate charset to hex / '-' / ':' (a predicate is always a
digest) and validates deal_id / seller, so a quote can never appear in a value.

Run:  python3 spike_s8_injection_guard.py
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

NET = "testnet"
ESCROW = os.environ.get("POD_ESCROW", "nft-repo-test-015.testnet")
BUYER = os.environ.get("POD_BUYER", ESCROW)
SELLER = os.environ.get("POD_SELLER", "nft-repo-loop4.testnet")
RPC = os.environ.get("POD_RPC", "https://rpc.testnet.fastnear.com")
ENV = dict(os.environ,
           NEAR_TESTNET_RPC=os.environ.get("NEAR_TESTNET_RPC", "https://rpc.testnet.fastnear.com"),
           PATH=os.path.join(HERE, "node_modules", ".bin") + os.pathsep + os.environ.get("PATH", ""))

FAILS = []


def chk(name, cond, detail=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name} " + (f"{detail}" if detail else ""))
    if not cond:
        FAILS.append(name)


def tx(method, args, signer, deposit=None):
    cmd = ["near", "call", ESCROW, method, json.dumps(args), "--accountId", signer,
           "--gas", "200000000000000", "--networkId", NET]
    if deposit:
        cmd += ["--deposit", str(deposit)]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, env=ENV, timeout=90)
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT"
    out = (p.stdout or "") + (p.stderr or "")
    flat = out.replace("\n", " ")
    ok = (p.returncode == 0) and ("Transaction Id" in out) and ("Failure" not in out) and ("panicked" not in flat)
    return ok, flat


def view(method, args=None):
    a = base64.b64encode(json.dumps(args or {}).encode()).decode()
    for _ in range(4):
        try:
            req = urllib.request.Request(RPC, data=json.dumps({
                "jsonrpc": "2.0", "id": 1, "method": "query",
                "params": {"request_type": "call_function", "finality": "final",
                           "account_id": ESCROW, "method_name": method, "args_base64": a}}).encode(),
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


def balance(a):
    try:
        req = urllib.request.Request(RPC, data=json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": "query",
            "params": {"request_type": "view_account", "finality": "final", "account_id": a}}).encode(),
            headers={"Content-Type": "application/json"})
        return int(json.load(urllib.request.urlopen(req, timeout=30))["result"]["amount"]) / 1e24
    except Exception:
        return None


def main():
    print("S8 — predicate-injection guard")
    b = balance(BUYER)
    if b is None or b < 3:
        print(f"  [ABORT] {BUYER} has {b} NEAR; need >= 3. Use POD_BUYER.")
        return 2

    dl = int(time.time() * 1e9) + 3600 * 10 ** 9
    inject = 'x","released":true,"deadline":1,"p":"'

    # 1. the view method must reject it outright
    chk("valid_predicate() rejects the injecting predicate",
        view("valid_predicate", {"p": inject}) is False, "")
    chk("valid_predicate() accepts a real 4-layer digest",
        view("valid_predicate", {"p": V.commit("anything")}) is True, V.commit("anything"))
    chk("valid_predicate() accepts a sha256 predicate",
        view("valid_predicate", {"p": "sha256:" + "a" * 64}) is True)
    chk("valid_id() rejects a quote in the seller",
        view("valid_id", {"s": 'eve"x'}) is False)

    # 2. create_deal must revert, not store a forged record
    deal = f"inj{int(time.time())}"
    ok, d = tx("create_deal", {"deal_id": deal, "seller": SELLER,
                               "predicate": inject, "deadline": str(dl)}, BUYER, 1)
    chk("create_deal REVERTS on an injecting predicate",
        (not ok) and "invalid predicate" in d, d[d.find("panicked"):d.find("panicked") + 60])
    r = view("get_deal", {"deal_id": deal})
    chk("  no deal was stored", isinstance(r, tuple) and "no deal" in str(r),
        "get_deal reverts with 'no deal'" if isinstance(r, tuple) else "A DEAL WAS STORED")

    # 3. the honest path still works, and no injected field can appear
    good = f"ok{int(time.time())}"
    pred = V.commit("a legitimate deliverable")
    ok, _ = tx("create_deal", {"deal_id": good, "seller": SELLER,
                               "predicate": pred, "deadline": str(dl)}, BUYER, 1)
    chk("create_deal still accepts a valid predicate", ok)
    j_raw = None
    end = time.time() + 25
    while time.time() < end:
        j_raw = view("get_deal", {"deal_id": good})
        if not (isinstance(j_raw, tuple) and "no deal" in str(j_raw)):
            break
        time.sleep(1.5)
    j = str(j_raw)
    chk("  the stored record has exactly one 'deadline' and one 'released'",
        j.count('"deadline"') == 1 and j.count('"released"') == 1, j[:120])

    # 4. deliver + the deadline cannot be influenced
    tx("deliver", {"deal_id": good, "payload": "a legitimate deliverable"}, SELLER)
    ok, d = tx("refund", {"deal_id": good}, BUYER)
    chk("refund before the real deadline still REVERTS", (not ok) and "deadline not reached" in d,
        d[d.find("panicked"):d.find("panicked") + 50])

    print()
    if FAILS:
        print(f"VERDICT: PARTIAL — failing steps: {FAILS}")
        return 1
    print("VERDICT: VALIDATED — a crafted predicate can no longer break out of its "
          "JSON field: the contract rejects it, stores no deal, and the honest path "
          "is unaffected with exactly one deadline/released in the record.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
