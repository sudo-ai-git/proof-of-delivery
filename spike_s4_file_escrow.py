#!/usr/bin/env python3
"""S4 spike — escrow a REAL FILE by sha256 identity.

Answers the design question directly: the buyer fixes the artifact's identity
(sha256) BEFORE funding; the contract hashes the delivered bytes itself and pays
only on an exact match. Proves it with real files, including a binary one and a
one-byte-substitution attack.

Run:  python3 spike_s4_file_escrow.py
"""
import base64
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))

NET = "testnet"
# Overridable so a judge can point the suite at their own accounts:
#   POD_ESCROW / POD_BUYER / POD_SELLER / POD_RPC
ESCROW = os.environ.get("POD_ESCROW", "nft-repo-test-015.testnet")
BUYER = os.environ.get("POD_BUYER", ESCROW)
SELLER = os.environ.get("POD_SELLER", "nft-repo-loop4.testnet")
RPC = os.environ.get("POD_RPC", "https://rpc.testnet.fastnear.com")


def require_key(acct):
    """Without local credentials the `near` CLI HANGS on an interactive prompt."""
    pats = [os.path.expanduser(f"~/.near-credentials/{NET}/{acct}.json"),
            os.path.expanduser(f"~/.near-credentials/{NET}/{acct}")]
    if not any(os.path.exists(p) for p in pats):
        print(f"  [ABORT] no local NEAR credentials for {acct}.\n"
              f"          Create/import one under ~/.near-credentials/{NET}/, or set\n"
              f"          POD_ESCROW / POD_BUYER / POD_SELLER to accounts you control.")
        sys.exit(2)
ENV = dict(os.environ,
           NEAR_TESTNET_RPC=os.environ.get("NEAR_TESTNET_RPC", "https://rpc.testnet.fastnear.com"),
           PATH=os.path.join(HERE, "node_modules", ".bin") + os.pathsep + os.environ.get("PATH", ""))

FAILS = []


def near_balance(acct):
    """Account balance in NEAR, or None."""
    try:
        req = urllib.request.Request(RPC, data=json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": "query",
            "params": {"request_type": "view_account", "finality": "final",
                       "account_id": acct}}).encode(), headers={"Content-Type": "application/json"})
        return int(json.load(urllib.request.urlopen(req, timeout=30))["result"]["amount"]) / 1e24
    except Exception:
        return None


def require_funds(acct, min_near, role):
    """Fail early and clearly — a dry account otherwise causes a confusing cascade."""
    b = near_balance(acct)
    if b is None or b < min_near:
        print(f"  [ABORT] {role} {acct} has {b} NEAR; this test escrows several 1 NEAR "
              f"deals and needs >= {min_near}.\n"
              f"          Fund it: near send-near <funded-acct> {acct} 10 --networkId testnet")
        sys.exit(2)
    return b


def chk(name, cond, detail=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name} " + (f"{detail}" if detail else ""))
    if not cond:
        FAILS.append(name)


def run_tx(method, args, signer, deposit=None, gas=200_000_000_000_000):
    cmd = ["near", "call", ESCROW, method, json.dumps(args), "--accountId", signer,
           "--gas", str(gas), "--networkId", NET]
    if deposit:
        cmd += ["--deposit", str(deposit)]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, env=ENV, timeout=90)
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT: the near CLI did not return within 90s (RPC stall?)"
    out = (p.stdout or "") + (p.stderr or "")
    flat = out.replace("\n", " ")
    bad = any(k in flat for k in ("Failure", "panicked", "does not satisfy", "no deal",
                                 "only the seller", "only the buyer", "requires a sha256 deal",
                                 "deadline not reached", "deadline in the past", "expected 64 hex"))
    ok = (p.returncode == 0) and ("Transaction Id" in out) and not bad
    if not ok and bad:
        # Extract the revert reason from the log line
        reason = "reverted"
        for marker in ["does not satisfy the predicate", "deadline not reached", "deal already settled", "no deal", "only the seller", "only the buyer", "requires a sha256 deal", "deadline in the past", "expected 64 hex chars"]:
            if marker in flat:
                reason = marker
                break
        return False, reason
    return ok, flat[-220:]


def view(method, args=None):
    a = base64.b64encode(json.dumps(args or {}).encode()).decode()
    for _ in range(5):
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


def poll(method, args, want, timeout=25):
    end = time.time() + timeout
    last = None
    while time.time() < end:
        last = view(method, args)
        if last == want:
            return last
        time.sleep(1.5)
    return last


def main():
    print("S4 spike — file escrow by sha256 identity (testnet)")
    require_key(BUYER)
    require_key(SELLER)
    require_funds(BUYER, 5.0, "buyer/escrow account")
    # two real files: A, and B = A with ONE byte changed
    A = bytes(range(256)) * 8 + b"NEAR hackathon deliverable v1\n"      # 2061 bytes, non-UTF8-safe
    B = bytearray(A)
    B[1000] ^= 0x01
    B = bytes(B)
    shaA = hashlib.sha256(A).hexdigest()
    shaB = hashlib.sha256(B).hexdigest()
    open(os.path.join(HERE, "asset_A.bin"), "wb").write(A)
    open(os.path.join(HERE, "asset_B.bin"), "wb").write(B)
    print(f"  asset_A.bin  {len(A)} bytes  sha256={shaA[:24]}…")
    print(f"  asset_B.bin  {len(B)} bytes  sha256={shaB[:24]}…  (1 byte differs)")

    # 0. the contract's sha256 must equal sha256sum
    txt = "hello file world"
    py = hashlib.sha256(txt.encode()).hexdigest()
    onchain = view("sha256_of", {"payload": txt})
    chk("contract sha256_of == sha256sum (python)", onchain == py, f"{str(onchain)[:16]}… vs {py[:16]}…")

    # 1. happy path: buyer commits to sha256(A), seller delivers A
    deal = f"f{int(time.time())}"
    deadline = int(time.time() * 1e9) + 3600 * 10 ** 9
    ok, d = run_tx("create_deal_sha", {"deal_id": deal, "seller": SELLER,
                                      "expected_sha256": shaA, "deadline": str(deadline)}, BUYER, deposit=1)
    chk("create_deal_sha (buyer commits to sha256 of the file)", ok, d[-110:])
    ok, d = run_tx("deliver_bytes", {"deal_id": deal,
                                     "b64": base64.b64encode(A).decode()}, SELLER)
    chk("deliver_bytes (binary file, base64)", ok, d[-110:])
    chk("delivery_ok -> true (contract hashed the bytes)", poll("delivery_ok", {"deal_id": deal}, True) is True)
    got = str(view("get_deal", {"deal_id": deal}))
    chk("stored digest == the file's sha256", shaA in got, "")
    ok, d = run_tx("release", {"deal_id": deal}, BUYER)
    chk("release pays the seller", ok, d[-110:])

    # 2. substitution attack: buyer commits to sha256(A), seller delivers B
    bad = f"x{int(time.time())}"
    run_tx("create_deal_sha", {"deal_id": bad, "seller": SELLER,
                               "expected_sha256": shaA, "deadline": str(deadline)}, BUYER, deposit=1)
    ok, d = run_tx("deliver_bytes", {"deal_id": bad,
                                     "b64": base64.b64encode(B).decode()}, SELLER)
    chk("substituted file delivered (tx itself succeeds)", ok, d[-90:])
    chk("delivery_ok -> false for the substituted file",
        poll("delivery_ok", {"deal_id": bad}, False) is False)
    ok, d = run_tx("release", {"deal_id": bad}, BUYER)
    chk("release REJECTS the substituted file", (not ok) and "does not satisfy" in d, d[-90:])

    # 3. wrong hash length is refused at creation
    ok, d = run_tx("create_deal_sha", {"deal_id": f"z{int(time.time())}", "seller": SELLER,
                                       "expected_sha256": "deadbeef", "deadline": str(deadline)}, BUYER, deposit=1)
    chk("create_deal_sha rejects a malformed sha256", (not ok) and "expected 64 hex" in d, d[-80:])

    print()
    if FAILS:
        print(f"VERDICT: PARTIAL — failing steps: {FAILS}")
        return 1
    print("VERDICT: VALIDATED — the buyer fixes the file's sha256 before funding; "
          "the contract decodes the delivered bytes, hashes them itself, and pays "
          "only on an exact match. A one-byte substitution is rejected on chain.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
