#!/usr/bin/env python3
"""S7 — a working agent-economy loop on NEAR: a buyer agent posts a job, seller
agents bid on it, the winner delivers, and the escrow settles.

This is the artifact the track actually asks for: *agents that earn, spend,
negotiate and settle* — not a lone contract.

THE FLOW (all settlement on chain, against the deployed contract):
  1. BUYER  posts a job: a spec, a budget, a deadline.
  2. SELLERS each quote a PRICE and commit to a CONTENT HASH for the artifact they
     would deliver. (This is where the buyer's expected hash comes from — the
     seller's own quote. See the README's "How a buyer knows it's the expected file".)
  3. BUYER  evaluates the quotes, picks the cheapest within budget, and escrows
     exactly that price against that seller's committed hash (create_deal_sha).
  4. WINNER produces the artifact and delivers the bytes (deliver_bytes).
  5. The CONTRACT hashes the bytes itself; anyone calls release(); the winner is paid.
  6. ROUND 2 is the adversarial case: the winner delivers DIFFERENT bytes than it
     committed to -> release reverts on chain -> the buyer is refunded at the deadline.

Honest boundary: the bidding round is coordinated by this script (a local
coordinator). Only the settlement is on chain. Making the round itself an
on-chain sealed-bid contract is the natural next step, and is called out as such.

Run:  python3 spike_s7_two_agent_loop.py
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
ESCROW = os.environ.get("POD_ESCROW", "nft-repo-test-015.testnet")
BUYER = os.environ.get("POD_BUYER", "nft-repo-test-014.testnet")
RPC = os.environ.get("POD_RPC", "https://rpc.testnet.fastnear.com")
ENV = dict(os.environ,
           NEAR_TESTNET_RPC=os.environ.get("NEAR_TESTNET_RPC", "https://rpc.testnet.fastnear.com"),
           PATH=os.path.join(HERE, "node_modules", ".bin") + os.pathsep + os.environ.get("PATH", ""))

FAILS = []


def chk(name, cond, detail=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name} " + (f"{detail}" if detail else ""))
    if not cond:
        FAILS.append(name)


# ── the agent-side primitives the product would ship ────────────────────────

class Account:
    def __init__(self, name):
        self.name = name

    def key_exists(self):
        return any(os.path.exists(os.path.expanduser(p))
                   for p in (f"~/.near-credentials/{NET}/{self.name}.json",
                             f"~/.near-credentials/{NET}/{self.name}"))

    def balance(self):
        try:
            req = urllib.request.Request(RPC, data=json.dumps({
                "jsonrpc": "2.0", "id": 1, "method": "query",
                "params": {"request_type": "view_account", "finality": "final",
                           "account_id": self.name}}).encode(),
                headers={"Content-Type": "application/json"})
            return int(json.load(urllib.request.urlopen(req, timeout=30))["result"]["amount"]) / 1e24
        except Exception:
            return None


class SellerAgent(Account):
    """Quotes a price and commits to the artifact it would deliver."""

    def __init__(self, name, unit_cost, markup, honest=True, salt=""):
        super().__init__(name)
        self.unit_cost = unit_cost
        self.markup = markup
        self.honest = honest          # honest=False -> delivers something else
        self.salt = salt

    def produce(self, job):
        """A deterministic artifact derived from the spec + this agent's own salt."""
        body = f"REPORT[{job['id']}] by {self.name}\n{job['spec']}\nsalt={self.salt}\n"
        return body.encode()

    def quote(self, job):
        size_kb = len(self.produce(job)) / 1024.0
        cost = self.unit_cost + self.unit_cost * size_kb
        price = cost * (1 + self.markup)
        art = self.produce(job)
        return {"seller": self.name, "price_near": round(price, 3),
                "commitment": hashlib.sha256(art).hexdigest(), "artifact": art}


class BuyerAgent(Account):
    def __init__(self, name, budget, escrow):
        super().__init__(name)
        self.budget = budget
        self.escrow = escrow

    def evaluate(self, quotes):
        """Cheapest quote within budget; ties broken by seller name (deterministic)."""
        afford = [q for q in quotes if q["price_near"] <= self.budget]
        afford.sort(key=lambda q: (q["price_near"], q["seller"]))
        return afford[0] if afford else None


# ── chain helpers ───────────────────────────────────────────────────────────

def tx(method, args, signer, deposit=None):
    cmd = ["near", "call", ESCROW, method, json.dumps(args), "--accountId", signer,
           "--gas", "200000000000000", "--networkId", NET]
    if deposit:
        cmd += ["--deposit", str(deposit)]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, env=ENV, timeout=90)
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT (RPC stall?)"
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


def poll_eq(method, args, want, timeout=25):
    end = time.time() + timeout
    last = None
    while time.time() < end:
        last = view(method, args)
        if last == want:
            return last
        time.sleep(1.5)
    return last


def main():
    print("S7 — agent economy loop: post -> bid -> award -> deliver -> settle\n")
    buyer = BuyerAgent(BUYER, budget=2.0, escrow=ESCROW)
    sellers = [
        SellerAgent(os.environ.get("POD_SELLER_A", "nft-repo-loop4.testnet"), unit_cost=0.25, markup=0.40, salt="A"),
        SellerAgent(os.environ.get("POD_SELLER_B", "nft-repo-test-013.testnet"), unit_cost=0.18, markup=0.90, salt="B"),
    ]
    for a in [buyer] + sellers:
        if not a.key_exists():
            print(f"  [ABORT] no local credentials for {a.name}. Use POD_BUYER/POD_SELLER_A/POD_SELLER_B.")
            return 2
    b = buyer.balance()
    if b is None or b < 4:
        print(f"  [ABORT] buyer {buyer.name} has {b} NEAR; the loop escrows ~2. Use POD_BUYER.")
        return 2

    job = {"id": f"job{int(time.time())}",
           "spec": "nightly market report for NEAR Intents volume",
           "budget": buyer.budget,
           "deadline_ns": int(time.time() * 1e9) + 3600 * 10 ** 9}

    # 1 + 2 ─────────────────────────────────────────────────────────────────
    print(f"1. BUYER {buyer.name} posts a job (budget {buyer.budget} NEAR): {job['spec']}")
    quotes = []
    for s in sellers:
        q = s.quote(job)
        quotes.append(q)
        print(f"2.   SELLER {s.name} quotes {q['price_near']} NEAR, commits sha256={q['commitment'][:16]}…")
    win = buyer.evaluate(quotes)
    if not win:
        print("  [ABORT] no quote within budget"); return 2
    others = [q["seller"] for q in quotes if q is not win]
    print(f"3. BUYER awards to {win['seller']} at {win['price_near']} NEAR "
          f"(outbid: {', '.join(others) or 'nobody'})")

    # 4 ─────────────────────────────────────────────────────────────────────
    ok, d = tx("create_deal_sha", {"deal_id": job["id"], "seller": win["seller"],
                                  "expected_sha256": win["commitment"],
                                  "deadline": str(job["deadline_ns"])}, buyer.name, deposit=win["price_near"])
    chk("BUYER escrows the winning price against the seller's committed hash", ok, d[-90:])

    # 5 ─────────────────────────────────────────────────────────────────────
    winner = next(s for s in sellers if s.name == win["seller"])
    ok, d = tx("deliver_bytes", {"deal_id": job["id"],
                                 "b64": base64.b64encode(win["artifact"]).decode()}, winner.name)
    chk("WINNER delivers the artifact it committed to", ok, d[-90:])
    chk("  the contract hashes it itself -> predicate satisfied",
        poll_eq("delivery_ok", {"deal_id": job["id"]}, True) is True)

    before = winner.balance()
    ok, d = tx("release", {"deal_id": job["id"]}, buyer.name)
    chk("anyone triggers release() -> the winner is PAID", ok, d[-90:])
    end = time.time() + 20
    after = winner.balance()
    while time.time() < end and after is not None and before is not None and after - before < win["price_near"] * 0.98:
        time.sleep(1.5)
        after = winner.balance()
    if before is not None and after is not None:
        print(f"      winner balance {before:.4f} -> {after:.4f} NEAR  (+{after-before:.4f})")
        chk("  the winner's balance rose by the awarded price",
            abs((after - before) - win["price_near"]) < 0.05)

    # 6 ─────────────────────────────────────────────────────────────────────
    print("\n6. ROUND 2 — adversarial seller: wins, then delivers DIFFERENT bytes")
    job2 = dict(job, id=f"job{int(time.time())}b",
                deadline_ns=int(time.time() * 1e9) + 45 * 10 ** 9)
    q2 = sellers[0].quote(job2)
    ok, _ = tx("create_deal_sha", {"deal_id": job2["id"], "seller": q2["seller"],
                                   "expected_sha256": q2["commitment"],
                                   "deadline": str(job2["deadline_ns"])}, buyer.name, deposit=q2["price_near"])
    chk("  buyer escrows for a second job", ok)
    swapped = q2["artifact"] + b"TAMPERED\n"
    ok, _ = tx("deliver_bytes", {"deal_id": job2["id"],
                                 "b64": base64.b64encode(swapped).decode()}, q2["seller"])
    chk("  the seller delivers substituted bytes (the tx itself is honest)", ok)
    chk("  the contract says NO", poll_eq("delivery_ok", {"deal_id": job2["id"]}, False) is False)
    ok, d = tx("release", {"deal_id": job2["id"]}, buyer.name)
    chk("  release REVERTS -> the seller is not paid", (not ok) and "does not satisfy" in d)
    print("      waiting for the deadline so the buyer can reclaim its escrow …")
    end = time.time() + 60
    while time.time() < end:
        ok, d = tx("refund", {"deal_id": job2["id"]}, buyer.name)
        if ok:
            break
        time.sleep(5)
    chk("  the buyer is REFUNDED at the deadline", ok, d[-90:] if ok else d[-90:])

    print()
    if FAILS:
        print(f"VERDICT: PARTIAL — failing steps: {FAILS}")
        return 1
    print("VERDICT: VALIDATED — a buyer agent posted a job, two seller agents quoted a "
          "price against a committed content hash, the buyer awarded and escrowed, the "
          "winner delivered and was paid, and an adversarial seller who swapped the "
          "artifact was not paid while the buyer was refunded. Real funds moved on NEAR.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
