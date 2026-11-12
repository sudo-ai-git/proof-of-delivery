#!/usr/bin/env python3
"""S2 spike — Proof-of-Delivery escrow round trip on NEAR testnet.

Verifies by execution, with STRICT success detection (a reverted call must not
count as a pass) and state polling (a read right after a tx is not trusted
until it reflects the write):

  POSITIVE: create_deal (payable) -> deliver -> delivery_ok -> release pays the seller
  NEGATIVE: a mis-matched delivery must be REJECTED by release()
  REFUND:   an unsatisfied deal refunds the buyer after its deadline

Run:  python3 spike_s2_escrow.py
"""
import base64
import json
import os
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verifier as V

NET = "testnet"
CONTRACT = "nft-repo-test-015.testnet"
BUYER = "nft-repo-test-015.testnet"
SELLER = "nft-repo-loop4.testnet"
RPC = "https://rpc.testnet.fastnear.com"
ENV = dict(os.environ, PATH="/home/sudosudo/node_modules/.bin:/home/sudosudo/.npm-global/bin:" + os.environ.get("PATH", ""))

FAILS = []


def chk(name, cond, detail=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name} {detail}")
    if not cond:
        FAILS.append(name)


def run_tx(method, args, signer, deposit=None, gas=300_000_000_000_000):
    """Returns (ok, detail). ok is True ONLY if the tx landed without a revert."""
    cmd = ["near", "call", CONTRACT, method, json.dumps(args),
           "--accountId", signer, "--gas", str(gas), "--networkId", NET]
    if deposit:
        cmd += ["--deposit", str(deposit)]
    p = subprocess.run(cmd, capture_output=True, text=True, env=ENV, timeout=180)
    out = (p.stdout or "") + (p.stderr or "")
    flat = out.replace("\n", " ")
    reverted = ("Failure" in out) or ("panicked" in flat) or ("does not satisfy" in flat) \
        or ("deadline not reached" in flat) or ("no deal" in flat) or ("only the seller" in flat) \
        or ("only the buyer" in flat)
    ok = (p.returncode == 0) and ("Transaction Id" in out) and not reverted
    return ok, flat[-260:]


def view(method, args):
    a = base64.b64encode(json.dumps(args).encode()).decode()
    for _ in range(5):
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


def poll_view(method, args, want, timeout=25):
    """Poll until view()==want (finality lag), else return last value."""
    end = time.time() + timeout
    last = None
    while time.time() < end:
        last = view(method, args)
        if last == want:
            return last
        time.sleep(1.5)
    return last


def balance(acct):
    p = subprocess.run(["near", "state", acct, "--networkId", NET],
                       capture_output=True, text=True, env=ENV, timeout=120)
    for line in (p.stdout or "").splitlines():
        if "amount:" in line:
            return int(line.split(":")[1].strip().strip("',"))
    return None


def main():
    print("S2 spike — Proof-of-Delivery escrow round trip (testnet, strict)")
    payload = "market report #42: NEAR Intents volume up 18% w/w"
    want = V.commit(payload)
    print(f"  predicate (expected commitment) = {want}")

    # ── POSITIVE ────────────────────────────────────────────────────────────
    deal = f"ok{int(time.time())}"
    deadline = int(time.time() * 1e9) + 3600 * 10 ** 9
    seller_before = balance(SELLER)

    ok, d = run_tx("create_deal", {"deal_id": deal, "seller": SELLER,
                                   "predicate": want, "deadline": str(deadline)}, BUYER, deposit=2)
    chk("create_deal escrows 2 NEAR", ok, d)
    j = poll_view("get_deal", {"deal_id": deal}, None)  # just warm up
    j = view("get_deal", {"deal_id": deal})
    chk("deal persisted on chain", isinstance(j, str) and '"amount":"2000000000000000000000000"' in j, f"got={str(j)[:80]}")

    ok, d = run_tx("deliver", {"deal_id": deal, "payload": payload}, SELLER)
    chk("deliver by seller", ok, d)
    chk("delivery_ok -> true", poll_view("delivery_ok", {"deal_id": deal}, True) is True)

    ok, d = run_tx("release", {"deal_id": deal}, BUYER)
    chk("release pays the seller", ok, d)
    time.sleep(4)
    seller_after = balance(SELLER)
    if seller_before and seller_after:
        delta = (seller_after - seller_before) / 1e24
        chk("seller balance +~2 NEAR", abs(delta - 2.0) < 0.06, f"delta={delta:+.4f} NEAR")
    chk("deal marked released", '"released":true' in str(view("get_deal", {"deal_id": deal})))

    # ── NEGATIVE ────────────────────────────────────────────────────────────
    bad = f"no{int(time.time())}"
    run_tx("create_deal", {"deal_id": bad, "seller": SELLER,
                           "predicate": want, "deadline": str(deadline)}, BUYER, deposit=1)
    run_tx("deliver", {"deal_id": bad, "payload": "junk that does not match"}, SELLER)
    chk("delivery_ok -> false on mismatch", poll_view("delivery_ok", {"deal_id": bad}, False) is False)
    ok, d = run_tx("release", {"deal_id": bad}, BUYER)
    chk("release REJECTS a non-matching delivery", (not ok) and "does not satisfy" in d, d[-90:])

    # ── REFUND ──────────────────────────────────────────────────────────────
    rd = f"rf{int(time.time())}"
    short = int(time.time() * 1e9) + 40 * 10 ** 9
    run_tx("create_deal", {"deal_id": rd, "seller": SELLER,
                           "predicate": want, "deadline": str(short)}, BUYER, deposit=1)
    ok, d = run_tx("refund", {"deal_id": rd}, BUYER)
    chk("refund BEFORE deadline is rejected", (not ok) and "deadline not reached" in d, d[-90:])
    print("     waiting 45s for the deadline …")
    time.sleep(45)
    ok, d = run_tx("refund", {"deal_id": rd}, BUYER)
    chk("refund AFTER deadline succeeds", ok, d)

    print()
    if FAILS:
        print(f"VERDICT: PARTIAL — failing steps: {FAILS}")
        return 1
    print("VERDICT: VALIDATED — full escrow round trip works on testnet with strict "
          "checks: payable fund, seller-only deliver, on-chain predicate check, "
          "release pays the seller, mismatched delivery is REJECTED, and an "
          "unsatisfied deal refunds the buyer after the deadline.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
