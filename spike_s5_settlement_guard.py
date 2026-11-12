#!/usr/bin/env python3
"""S5 regression — the settlement guard.

A security review of pod-3 found that release()/refund() never checked the
`released` flag, so BOTH were re-callable: release() twice paid the seller twice,
and release-then-refund paid the seller and then the buyer — draining other
deals' escrow. Reproduced on chain: one 1-NEAR deal paid out 2.2007 NEAR.

This spike is the regression test for the fix. It asserts the *negative* cases,
which is the part the earlier suites never covered.

Run:  python3 spike_s5_settlement_guard.py
"""
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
BUYER = os.environ.get("POD_BUYER", "nft-repo-test-015.testnet")
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
        return False, "TIMEOUT: the near CLI did not return within 90s (RPC stall?)"
    out = (p.stdout or "") + (p.stderr or "")
    flat = out.replace("\n", " ")
    reverted = ("Failure" in out) or ("panicked" in flat)
    ok = (p.returncode == 0) and ("Transaction Id" in out) and not reverted
    return ok, flat


def view(method, args=None):
    a = json.dumps(args or {}).encode()
    import base64
    a = base64.b64encode(a).decode()
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


def balance(acct):
    r = json.load(urllib.request.urlopen(urllib.request.Request(RPC, data=json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "query",
        "params": {"request_type": "view_account", "finality": "final",
                   "account_id": acct}}).encode(), headers={"Content-Type": "application/json"}), timeout=30))
    return int(r["result"]["amount"]) / 1e24


def main():
    print("S5 spike — settlement guard (double-payout regression)")
    b = balance(BUYER)
    if b < 5:
        print(f"  [ABORT] {BUYER} has {round(b,3)} NEAR; need >= 5.\n"
              f"          Fund it: near send-near <funded> {BUYER} 10 --networkId testnet")
        return 2

    payload = "settlement guard payload"
    pred = V.commit(payload)
    deadline = int(time.time() * 1e9) + 3600 * 10 ** 9

    # ── case 1: release twice ───────────────────────────────────────────────
    d1 = f"g1{int(time.time())}"
    tx("create_deal", {"deal_id": d1, "seller": SELLER, "predicate": pred, "deadline": str(deadline)}, BUYER, 1)
    tx("deliver", {"deal_id": d1, "payload": payload}, SELLER)
    before = balance(SELLER)
    ok1, _ = tx("release", {"deal_id": d1}, BUYER)
    time.sleep(3)
    after1 = balance(SELLER)
    ok2, out2 = tx("release", {"deal_id": d1}, BUYER)
    time.sleep(3)
    after2 = balance(SELLER)
    chk("first release pays the seller", ok1 and after1 > before, f"+{after1-before:.4f} NEAR")
    chk("second release REVERTS (deal already settled)", (not ok2) and "already settled" in out2,
        "revert 'deal already settled'" if not ok2 else "STILL PAYABLE")
    # The security property: the rejected call moved no money. Measured across the
    # rejected call only (a wide window can catch unrelated payouts still landing).
    chk("rejected call pays nothing", abs(after2 - after1) < 0.02,
        f"delta across the rejected call = {after2-after1:+.4f} NEAR")

    # ── case 2: release then refund ─────────────────────────────────────────
    d2 = f"g2{int(time.time())}"
    short = int(time.time() * 1e9) + 20 * 10 ** 9
    tx("create_deal", {"deal_id": d2, "seller": SELLER, "predicate": pred, "deadline": str(short)}, BUYER, 1)
    tx("deliver", {"deal_id": d2, "payload": payload}, SELLER)
    okr, _ = tx("release", {"deal_id": d2}, BUYER)
    chk("release on the second deal succeeds", okr)
    print("     waiting 25s for the deadline …")
    time.sleep(25)
    okf, outf = tx("refund", {"deal_id": d2}, BUYER)
    chk("refund AFTER release REVERTS (no double payout)", (not okf) and "already settled" in outf,
        "revert 'deal already settled'" if not okf else "REFUND PAID OUT")

    # ── case 3: the honest paths still work ─────────────────────────────────
    d3 = f"g3{int(time.time())}"
    tx("create_deal", {"deal_id": d3, "seller": SELLER, "predicate": pred, "deadline": str(deadline)}, BUYER, 1)
    tx("deliver", {"deal_id": d3, "payload": payload}, SELLER)
    chk("a fresh deal is still releasable", tx("release", {"deal_id": d3}, BUYER)[0])
    end = time.time() + 20
    j = str(view("get_deal", {"deal_id": d3}))
    while time.time() < end and '"released":true' not in j:
        time.sleep(1.5)
        j = str(view("get_deal", {"deal_id": d3}))
    chk("settled deal is marked released and its slot cleared",
        '"released":true' in j and '"commitment":""' in j, j[:130])

    # ── case 4: deliver must NOT be able to re-arm a settled deal ───────────
    # This is the case spike_s5 originally missed: pod-4 guarded release/refund
    # but deliver() re-serialised the record with released=false and refilled the
    # commitment slot, so release -> deliver -> release paid twice (measured: a
    # 1-NEAR deal paid 1.9996 NEAR). The guard belongs on every state transition,
    # not just on the payout functions.
    d4 = f"g4{int(time.time())}"
    tx("create_deal", {"deal_id": d4, "seller": SELLER, "predicate": pred,
                       "deadline": str(deadline)}, BUYER, 1)
    tx("deliver", {"deal_id": d4, "payload": payload}, SELLER)
    okr1, _ = tx("release", {"deal_id": d4}, BUYER)
    chk("re-arm: first release pays", okr1)
    okd, dd = tx("deliver", {"deal_id": d4, "payload": payload}, SELLER)
    chk("  re-delivering a SETTLED deal REVERTS", (not okd) and "already settled" in dd,
        "revert 'deal already settled'" if not okd else "RE-ARMED")
    okr2, dr2 = tx("release", {"deal_id": d4}, BUYER)
    chk("  the follow-up release REVERTS too", (not okr2) and "already settled" in dr2,
        "revert 'deal already settled'" if not okr2 else "PAID AGAIN")
    okf2, df2 = tx("refund", {"deal_id": d4}, BUYER)
    chk("  and refund on a settled deal REVERTS", (not okf2) and "already settled" in df2,
        "revert 'deal already settled'" if not okf2 else "PAID AGAIN")

    print()
    if FAILS:
        print(f"VERDICT: PARTIAL — failing steps: {FAILS}")
        return 1
    print("VERDICT: VALIDATED — release() and refund() are single-shot: a repeat call "
          "and a release-then-refund both revert with 'deal already settled', and the "
          "honest path still pays exactly once.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
