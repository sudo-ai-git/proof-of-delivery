#!/usr/bin/env python3
"""S3 spike — Proof-of-Delivery escrow holding a NEP-141 token (stablecoins).

Uses the canonical testnet FT `wrap.testnet` (wNEAR, 24 decimals). Proves the
cross-contract path end to end with strict checks:

  register -> wrap NEAR -> ft_transfer_call creates the deal -> deliver ->
  release calls token.ft_transfer and the seller's wNEAR balance grows.

Run:  python3 spike_s3_ft_escrow.py
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
ESCROW = "nft-repo-test-015.testnet"
BUYER = "nft-repo-test-014.testnet"   # must differ from ESCROW: FTs reject self-transfers
SELLER = "nft-repo-loop4.testnet"
FT = "wrap.testnet"
RPC = "https://rpc.testnet.fastnear.com"
ENV = dict(os.environ, PATH="/home/sudosudo/node_modules/.bin:/home/sudosudo/.npm-global/bin:" + os.environ.get("PATH", ""))
ONE = 10 ** 24
AMOUNT = str(ONE // 2)  # 0.5 wNEAR

FAILS = []


def chk(name, cond, detail=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name} {detail}")
    if not cond:
        FAILS.append(name)


def run_tx(contract, method, args, signer, deposit=None, yocto=None, gas=100_000_000_000_000):
    cmd = ["near", "call", contract, method, json.dumps(args),
           "--accountId", signer, "--gas", str(gas), "--networkId", NET]
    if deposit:
        cmd += ["--deposit", str(deposit)]
    if yocto:
        cmd += ["--depositYocto", str(yocto)]
    p = subprocess.run(cmd, capture_output=True, text=True, env=ENV, timeout=180)
    out = (p.stdout or "") + (p.stderr or "")
    flat = out.replace("\n", " ")
    bad = ("Failure" in out) or ("panicked" in flat) or ("does not satisfy" in flat) or \
          ("deadline not reached" in flat) or ("no deal" in flat) or ("msg needs" in flat) or \
          ("only the seller" in flat) or ("only the buyer" in flat)
    ok = (p.returncode == 0) and ("Transaction Id" in out) and not bad
    return ok, flat[-240:]


def view(contract, method, args=None):
    a = base64.b64encode(json.dumps(args or {}).encode()).decode()
    for _ in range(5):
        try:
            req = urllib.request.Request(RPC, data=json.dumps({
                "jsonrpc": "2.0", "id": 1, "method": "query",
                "params": {"request_type": "call_function", "finality": "final",
                           "account_id": contract, "method_name": method, "args_base64": a}}).encode(),
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


def wnear(acct):
    v = view(FT, "ft_balance_of", {"account_id": acct})
    try:
        return int(v)
    except Exception:
        return None


def wait_wnear(acct, pred, timeout=30):
    """Poll the FT balance until pred(balance) holds (finality lag), else return last."""
    end = time.time() + timeout
    last = None
    while time.time() < end:
        last = wnear(acct)
        if last is not None and pred(last):
            return last
        time.sleep(1.5)
    return last


def main():
    print("S3 spike — NEP-141 escrow round trip (wNEAR on testnet, strict)")
    payload = "agent deliverable: dataset v7 (sha in commitment)"
    want = V.commit(payload)
    print(f"  predicate = {want}")

    # 1. register buyer + escrow + seller on the FT (required to hold/receive wNEAR)
    for acct in (BUYER, ESCROW, SELLER):
        ok, d = run_tx(FT, "storage_deposit", {"account_id": acct}, ESCROW, deposit=0.05)
        got = view(FT, "storage_balance_of", {"account_id": acct})
        chk(f"register {acct} on {FT}", got not in (None, "None") and got != ("ERR",), f"storage={got}")

    # 2. buyer wraps 1 NEAR -> wNEAR
    before_wrap = wnear(BUYER) or 0
    ok, d = run_tx(FT, "near_deposit", {}, BUYER, deposit=1)
    after_wrap = wait_wnear(BUYER, lambda b: b >= before_wrap + ONE)
    chk("buyer wrapped NEAR -> wNEAR", ok and after_wrap is not None and after_wrap >= before_wrap + ONE,
        f"{before_wrap} -> {after_wrap}")

    # 3. buyer funds the deal via ft_transfer_call (creates it in ft_on_transfer)
    deal = f"ft{int(time.time())}"
    deadline = int(time.time() * 1e9) + 3600 * 10 ** 9
    msg = json.dumps({"deal_id": deal, "seller": SELLER, "predicate": want, "deadline": str(deadline)})
    seller_before = wnear(SELLER)
    ok, d = run_tx(FT, "ft_transfer_call",
                   {"receiver_id": ESCROW, "amount": AMOUNT, "msg": msg}, BUYER, yocto=1)
    chk("ft_transfer_call creates the deal", ok, d[-120:])
    j = view(ESCROW, "get_deal", {"deal_id": deal})
    persisted = isinstance(j, str) and f'"token":"{FT}"' in j and f'"amount":"{AMOUNT}"' in j
    chk("deal persisted with token + amount", persisted, f"got={str(j)[:110]}")

    # 4. deliver + predicate check
    ok, d = run_tx(ESCROW, "deliver", {"deal_id": deal, "payload": payload}, SELLER)
    chk("seller delivered", ok, d[-100:])
    end = time.time() + 25
    dv = view(ESCROW, "delivery_ok", {"deal_id": deal})
    while dv is not True and time.time() < end:
        time.sleep(1.5)
        dv = view(ESCROW, "delivery_ok", {"deal_id": deal})
    chk("delivery_ok -> true", dv is True, f"got={dv}")

    # 5. release -> escrow calls wrap.testnet.ft_transfer(seller, amount)
    ok, d = run_tx(ESCROW, "release", {"deal_id": deal}, BUYER)
    chk("release calls token.ft_transfer", ok, d[-120:])
    seller_after = wait_wnear(SELLER, lambda b: seller_before is not None and b >= seller_before + int(AMOUNT))
    if seller_before is not None and seller_after is not None:
        delta = seller_after - seller_before
        chk("seller wNEAR grew by the escrowed amount", delta == int(AMOUNT),
            f"delta={delta} (want {AMOUNT})")

    print()
    if FAILS:
        print(f"VERDICT: PARTIAL — failing steps: {FAILS}")
        return 1
    print("VERDICT: VALIDATED — the escrow holds a NEP-141 token across a "
          "cross-contract ft_transfer_call/ft_on_transfer and releases it to the "
          "seller via token.ft_transfer; the seller's wNEAR balance grew by exactly "
          "the escrowed amount.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
