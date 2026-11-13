# Proof-of-Delivery — escrowed agent payments that release only on verified delivery

**NEAR HACKATHON entry · tracks: `swarms`, `defi`, `open`, `agents`**

> Track choice is deliberate, not incidental, and it is driven by the live
> submission directory rather than by taste. At the time of writing the field was
> **649 projects**, and the crowding is wildly uneven: `security` ~308, `agents`
> ~302, `realworld`/`open` ~127, `business` ~122, `privacy` ~116, **`defi` ~110**,
> **`swarms` ~61**, `thesis` ~55. A submission is scored separately in every track
> it lists (still one submission), so the thin track is where a deeply-verified
> settlement primitive has its best shot.
>
> - **`swarms`** — the best ratio in the field (~61 for 3 slots). A bidding round
>   with escrowed settlement *is* the "coordination market / intent-based
>   settlement" the track asks for. Primary.
> - **`defi`** — a NEP-141 escrow that pays only on a verifiable delivery is a
>   settlement primitive; here the mechanism is the *core* of the track rather
>   than a guest.
> - **`open`**, **`agents`** — cheap, legitimate extras.
> - **`security` deliberately dropped.** It is the second-largest field, and an
>   escrow contract is not a security tool — the reviewers said so bluntly.

## The problem (one line)

AI agents can pay each other, but a buyer agent has no way to trust that a
seller agent actually delivered — so agent commerce runs on trust or a human
referee. This contract removes the referee.

## A working agent-economy loop (the demo)

Not a contract looking for users — two agents transacting. `spike_s7_two_agent_loop.py`
runs the whole loop against the deployed contract; every settlement below is real:

```
1. BUYER  posts a job: a spec, a budget (2 NEAR), a deadline
2. SELLER loop4 quotes 0.385 NEAR, committing sha256=4891535c…   <- a price AND a promise
   SELLER 013   quotes 0.377 NEAR, committing sha256=2ee2a838…      about WHAT it will deliver
3. BUYER  awards to 013 at 0.377 (outbid: loop4) and escrows against
          013's COMMITTED HASH — this is where the buyer's expected
          hash comes from, not from a guess
4. WINNER produces the artifact and delivers the bytes
5. CONTRACT hashes the bytes itself -> predicate satisfied -> release() -> winner PAID
          winner balance 9.9961 -> 10.3731 NEAR  (+0.3770)
6. ROUND 2, adversarial: the seller wins, then delivers SUBSTITUTED bytes
          -> delivery_ok = false -> release() REVERTS -> the seller is not paid
          -> at the deadline the buyer is REFUNDED
```

The quote carries the commitment, so a seller commits to *what* it will deliver
before it is paid — and the contract holds it to that, byte for byte.

**Honest boundary:** the bidding round is coordinated by this script (a local
coordinator). Only the settlement is on chain. Making the round itself an
on-chain sealed-bid contract is the natural next step.

## What it is

A **Proof-of-Delivery escrow**: a buyer locks funds — **native NEAR or any
NEP-141 stablecoin** — in a deal with a machine-checkable release predicate.
The seller delivers an artifact. **Any** caller can then trigger `release()`,
and the funds move to the seller *iff* the delivered artifact satisfies the
buyer's predicate — checked deterministically **on chain**. If the deadline
passes with no satisfying delivery, the buyer is refunded.

The predicate has two kinds, and the deal records which one it uses.

**`sha256:<hex>` — real artifacts (the one that matters).** The buyer commits the
file's sha256; the seller delivers the bytes; the contract decodes and hashes them
**itself**, so a seller cannot fake delivery by asserting a digest. 256-bit and
adversarial-safe.

**A 4-layer integer checksum — a reproducible tamper-detection demo.** Small,
dependency-free, and what the browser demo mirrors. It is **not** a security
primitive, and we measured exactly how weak it is:

```
commitment(payload) = "fnv8-sum2-lin2-odd2"
  L0  FNV-1a-32 over the low byte of each code unit   <- the only layer that sees order
  L1  sum(byte + index)     mod 231
  L2  sum(byte*22 + index)  mod 231
  L3  count(odd bytes)      mod 37
```

### Why the 4-layer checksum is a demo, not a guard (measured, not asserted)

L1 and L2 are both determined by the *same* quantity:

```
L1 = sum(b_i) + n(n-1)/2        L2 = 22*sum(b_i) + n(n-1)/2
```

so together they carry no more than the byte sum, and — with L3, the odd-byte
count — all three are **invariant under permuting the payload**. Only L0 sees byte
order, and L0 is 32-bit non-cryptographic FNV-1a.

So a **full 4-layer collision is a ~2^16 birthday over permutations**, not a 2^53
search. `spike_s6_commitment_collision.py` finds one in **0.8 s / 37,417
permutations**, and `spike_s1_commitment_parity.py` confirms it against the
**live contract**:

```
payload A = '-EIL0OY-0P0DEDRV'
payload B = 'DE00I0YOD--LPVER'
commitment on both = a4445cec-26-a4-07
```

Two different payloads, one commitment, accepted by the deployed contract. Do not
use this kind where a counterparty could profit from swapping the artifact — use
`sha256:`. It remains genuinely useful for *detecting accidental corruption* and
for demonstrating the enforcement mechanism, and a single-character edit still
breaks ≥3 of the 4 layers (`mismatch_count()` reports which).

**Three independent implementations agree byte-for-byte** — the live contract,
`verifier.py`, and the JS in `demo/index.html`. Re-runnable:
`python3 spike_s1_commitment_parity.py` → 20/20 three-way.

## What this actually verifies — and what it does not

It verifies **byte identity**: the artifact handed over is exactly the artifact
whose hash the buyer committed to. The contract hashes the delivered bytes itself,
so the seller cannot fake *that*.

It does **not** verify satisfaction, quality or usefulness. An agent-protocol
review put it precisely: *"hash equality proves integrity, not satisfaction."* A
seller who commits the sha256 of a one-line junk file, wins on price, and delivers
exactly that junk has **broken no rule** — `delivery_ok` is true and the contract
pays in full. In the loop above, the buyer awards the cheapest quote among
artifacts it has never seen and cannot inspect, so the seller's dominant strategy
is to commit to nothing. That is a lemons market with a cryptographic receipt.

This is a **settlement primitive, not a quality oracle.** The obvious next design
step is to make judgment an *address* rather than a string prefix —
`evaluator: AccountId` plus a `verdict(deal_id, ok, spec_hash)` call, the shape
ERC-8183 uses — so an escrow can defer to a TEE signer, an LLM jury, a human, or
a stake-and-slash game, with the sha256 path as the zero-configuration default.

What the predicate **does** verify today, verified on chain:

- the delivered bytes hash to the value the buyer fixed *before* funding;
- a substituted artifact cannot satisfy it — one byte different reverts;
- nobody can settle twice (see **Security**);
- a crafted predicate cannot forge the deal's own fields (see **Security**).

## Try the predicate with no chain at all

Open `demo/index.html` in a browser: type a deliverable, watch the 4 layers
recompute live, press **Change one character** and see ≥3 layers flip to
BROKEN. No server, no wallet, no account.

## How a buyer knows it's the expected file

The escrow does **not** discover what you wanted — it enforces payment only
against a hash you fixed **before** funding. The artifact's identity must come
from somewhere the buyer trusts *first*:

| where the buyer gets the hash | example |
|---|---|
| the seller's listing / manifest (buy a specific artifact by its hash) | "dataset v7, sha256 = 3f9a…" |
| a prior agreement on a shared spec, both sides hash it | a contract PDF, an API schema |
| a third party's published checksum | a release page, an audited artifact |
| a merkle root, for a set of files | a bundle, a directory tree |

There are two predicate kinds, and the deal stores which one it uses:

- **`sha256:<hex>` — real files.** The buyer calls `create_deal_sha(...)` with the
  file's sha256. The seller delivers the bytes (`deliver_bytes` for binary, as
  base64); the contract **decodes and hashes them itself**, so the seller cannot
  fake delivery by asserting a digest.
- **the 4-layer commitment — short payloads and tamper demos.** No prefix.

> **Honest limit — measured, not guessed.** The 4-layer commitment is not a
> security primitive: L1/L2/L3 are invariant under permuting the payload, so its
> collision resistance collapses to the 32-bit non-cryptographic FNV-1a and a
> full collision takes ~2^16 permutations. We found one in **0.8 s** and
> confirmed it on the live contract (`spike_s6_commitment_collision.py` /
> `spike_s1_commitment_parity.py`). Use `sha256:` for anything a counterparty
> could profit from swapping.

**Verified end to end (spike S4, testnet):** a 2,078-byte binary file was
escrowed by its sha256 and released; a second file differing by **one byte** was
delivered instead and the release **reverted on chain**. `sha256_of()` on the
contract matches `sha256sum` exactly.

**Large files.** A contract call can only carry a few hundred KB, so inline
delivery covers documents, datasets-in-a-call and small artifacts. For a large
file the designed path (not yet built) is a **merkle root** over fixed-size
chunks delivered across several calls, plus a **dispute window** after delivery
during which the buyer can challenge — because a contract cannot fetch a URL, so
"the bytes are retrievable *and* hashed to the commitment" has to be a windowed
promise rather than an instant check.



## NEAR's role (concrete)

NEAR holds the money and enforces the rule: escrow custody, the seller-only
delivery check, the deterministic predicate evaluation, and the payout/refund
transfer all live in the contract. No backend can switch the release rule off,
and no arbiter is required. This is money that only moves when the *condition*
is met — the programmable-money primitive the track asks for.

## Security: three real bugs, found by review, reproduced, fixed, pinned

None of these were caught by the project's own suites. Two came from adversarial
review that was specifically told to attack the state machine and the parser — and
**one of them defeated the fix for another**, which is the interesting part.

### 1. Repeat payout (`pod-3` → `pod-4`)

`release()` wrote `released: true` but never **checked** it, and `refund()`
ignored it. So `release()` was repeatable, and release-then-refund paid both
sides. **Reproduced: one 1-NEAR deal paid 2.2007 NEAR.** Fixed with an
`already settled` assert in both functions.

### 2. The fix was defeatable — `deliver()` re-armed it (`pod-4` → `pod-6`)

This is the one worth reading. `deliver()` and `deliver_bytes()` had **no settled
check**, and they re-serialize the record with `released = false` while **refilling
the commitment slot that `release()` clears**. So the seller could re-arm a settled
deal:

```
release #1     -> PAID      +0.9998
deliver AGAIN  -> ACCEPTED  (rewrites released=false, refills the commitment)
release #2     -> PAID AGAIN +0.9998
TOTAL for ONE 1-NEAR deal: 1.9996 NEAR
```

The README had claimed the two barriers were "independent" — **they were not**,
because a delivery-writing path could set both. And because every deposit sits in
one pooled balance, this escalates from "I get my own NEAR twice" to *draining
every native deal in the escrow*. Our own regression missed it because it only
tested release→release and release→refund, never the deliver path.

Fixed in `pod-6`: a settled deal is **terminal**, asserted in `deliver` *and*
`deliver_bytes`. The lesson is in the code comment — the guard belongs on **every
state transition**, not just the payout functions.

### 3. Predicate injection forged the deal's own fields (`pod-5`)

The deal record is hand-built by concatenation and the parser returns the *first*
match for a key. `predicate` was free text, so this predicate

```
x","released":true,"deadline":1,"p":"
```

broke out of its string and injected a second `deadline` **before** the real one.
Since `deliver()` re-serializes via `numField(...,"deadline")`, the deal's
effective deadline became `1` — so after a seller delivered, **`refund` succeeded
immediately**: the buyer reclaims the escrow and keeps the artifact. A theft race,
not just a lock. (Injecting `released:true` instead strands the funds.)

Fixed in `pod-5`: `valid_predicate` / `valid_id` reject quote, backslash and
non-printable bytes in `predicate`, `deal_id` and `seller`, in both `create_deal`
and `ft_on_transfer` — a quote can no longer appear inside a value.

### Known, documented, NOT fixed

**Settlement is written before the payout promise.** `release()`/`refund()` set
`released = true` and clear the commitment, *then* issue the transfer. On NEAR a
failed promise does not roll back the caller's state, so if the transfer fails the
deal reads settled while the money never moved — and neither `release` nor `refund`
will touch it again. Realistic triggers: a NEP-141 seller who was never registered
for storage (the common case for a fresh account), a `seller` account that does
not exist, or a payout that runs out of gas. **Do not put real value behind this
without adding a promise callback that un-settles the deal on failure.**

### Regression suite

```
spike_s5_settlement_guard.py  -> 11/11  (repeat release, release→refund, AND the
                                          deliver re-arm: deliver→release→deliver→release)
spike_s8_injection_guard.py   ->  9/9   (crafted predicates rejected; record clean)
exploit_repro_pod3.txt                  (the measured 2.2007 NEAR before/after)
```

A security track that only shows green happy-path tests is showing nothing. This
section, the repro numbers, and the two regressions are the evidence that the state
machine and the parser were actually attacked.



## Verified on NEAR testnet — every transaction

Contract: **`nft-repo-test-015.testnet`** · code_hash **`78AZtabZdjQDU83EWuuA4QZ2h9JtbUSXZmLhtUGFJS3T`**
— the deployed WASM, verifiable on-chain via `near state`. Build the contract
locally with `npm run build` (wasm32-unknown-unknown target) to reproduce the
artifact; note that the on-chain code was built from the committed source at
deploy time and the local build may differ if sources have changed since.
```


```bash
python3 -c "import hashlib,base64;w=open('build/release/proof-of-delivery.wasm','rb').read();print(len(w),'bytes');print(base64.b64encode(hashlib.sha256(w).digest()))"
# 33785 bytes -> the base58 form of that sha256 is the local build hash;
```

Explorer links (`https://testnet.nearblocks.io/txns/<hash>`). Every one of these
was re-queried against the RPC and resolves; the last row is a **failure**, by
design:

| suite | step | transaction |
|---|---|---|
| — | deploy `pod-3` | `C7iMNjYXdZKpvzJjHSKDcJxmQWr36D3TeUVrRveMcebo` |
| S2 | `create_deal` — 2 NEAR escrowed | `5D3sgBtEm3WveXact9pGhWoZJ2JBSnS6VDUvUXLgwQxf` |
| S2 | `deliver` (seller) | `FaM3f4nr8EXdxG5qz3vPrc9xihCD9Tuywr132CWMWyks` |
| S2 | `release` — pays the seller +2 NEAR | `9pAse5XU2s1Ekn85pz3uMLzHY9ZA8JNqYwX2pr4ZtSzR` |
| S2 | `refund` after the deadline | `Aw8y9cCf92JcHzhNvWMHQ2BX2aEkWgrDxMdeEBkxft4t` |
| S3 | `ft_transfer_call` — creates the deal | `HmXhLXPAXYFzhjjUDxuRrdfNvJroG88fd2igXTkei3g5` |
| S3 | `deliver` (seller) | `ArGfewebuUriV3BopzcqMJQZdxUqTtnzP9hMJETv65RW` |
| S3 | `release` → `token.ft_transfer` | `2gfkaT76MkjLurJey6SixDzpYyRRhZXGK2VmMDQmBuNj` |
| S4 | `create_deal_sha` — buyer commits a sha256 | `5MDpT7kk5yA8CiqKJyESTZH4rcpnhitzQ6XmqaTLdm89` |
| S4 | `deliver_bytes` — binary file, base64 | `DFnU3j6oSCPJeyw5qdgLTCNaCLQ3boiDD7hzL9TookeZ` |
| S4 | `release` — pays for the **correct** file | `4Ku5QTBJadTypo44rsmsCHXbAi3ez8cKevw2csvEvJFU` |
| S4 | substituted file delivered (the tx itself is honest) | `EqSxt4eL6UEPTz3Te5FGBYdFMTRSPRbfPQ4AFh5nPmKW` |
| S4 | **`release` on the substituted file → FAILURE** | `Ed4UnTwQAHr5DQGsCSgw8jtg3aSE1bn7TRHh7XEZRnC1` |
| S7 | award + escrow against the seller's **committed** hash | `91AMDus7gWTrAEdTBjENcxXKNmcRPTWEnxMLud1LhqqB` |
| S7 | winner delivers the committed bytes | `CBaSzVzyvcJmN165qn93bsTPRUy961qoQs9uB9CHsQKy` |
| S7 | `release` → **winner paid** (+0.3770 NEAR) | `6Kv3ZqxTN8vBTgSf1knvDKu9CPjMWzjTLeSrnpjvTNv2` |
| S7 | refund after the adversarial round | `47a9ozsJicQ2jH391YYRKPv71hgSNESz2PoLa9LgHGrg` |

You do not have to trust the explorer UI (it also rate-limits bots). Query the
chain yourself:

```bash
# the revert — expect status: Failure, "delivery does not satisfy the predicate"
curl -s https://rpc.testnet.fastnear.com -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tx","params":{"tx_hash":"Ed4UnTwQAHr5DQGsCSgw8jtg3aSE1bn7TRHh7XEZRnC1","sender_account_id":"nft-repo-test-015.testnet","wait_until":"FINAL"}}' \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['result']['status'])"

# the deployed code is this repo's build
python3 -c "import hashlib;print(hashlib.sha256(open('build/release/proof-of-delivery.wasm','rb').read()).hexdigest())"
```

## Screenshots

Committed under [`screenshots/`](screenshots/) — generated from real output, not mockups:

| file | shows |
|---|---|
| `screenshots/10_agent_loop.png` | **the agent-economy loop** — buyer posts, two sellers quote price + sha256, award, escrow, delivery, payout, adversarial swap → revert → refund |
| `screenshots/09_chain_state.png` | live chain read: `code_hash` and the FAILURE/SUCCESS verdict per transaction |
| `screenshots/08_file_escrow.png` | the file run — sha256 escrow, one-byte substitution rejected (tx links visible) |
| `screenshots/04_escrow_roundtrip.png` | native-NEAR run — release pays, tamper reverts, refund (tx links visible) |
| `screenshots/05_stablecoin.png` | NEP-141 run — VERDICT VALIDATED (tx links visible) |
| `screenshots/03_verify_all.png` | `verify_all.py` → ALL GATES PASS (4/4) |
| `screenshots/01/02_commitment_*.png` | the browser demo, satisfied → tampered |
| `screenshots/demo.mp4` | 9s screen recording of the demo interaction |

`x_demo/make_assets.py` regenerates all of them; `x_demo/POST.md` is the demo post.

## Do X → see Y (a judge can run every line)

**Prereq:** Node.js (`npm install` fetches the contract toolchain), the `near`
CLI for testnet, and `python3`. No API keys, no secrets.

```bash
npm install                       # near-sdk-as@3.2.3 + asbuild (provides `asb`)
export PATH="$PWD/node_modules/.bin:$PATH"

# The JS near-cli defaults to the DEPRECATED rpc.testnet.near.org, which 429s
# intermittently and makes test runs flaky. Point it at a working node:
export NEAR_TESTNET_RPC=https://rpc.testnet.fastnear.com
```

The three `spike_s*.py` scripts send real transactions, so they need a funded
testnet account (they escrow 2–4 NEAR in total and check the balance up front
with a clear message if it is too low). `verify_all.py`, `verifier.py` and
`demo/index.html` need no funds at all — `verify_all.py` only reads the chain.

**Start here — one command runs every gate** (offline + live parity):

```bash
python3 verify_all.py --build --selftest
#   -> [PASS] G1 build (33,785 bytes, key exports present)
#      [PASS] G2 golden vectors           (Python matches values the CONTRACT produced)
#      [PASS] G3 tamper breaks >=3 layers
#      [PASS] G4 live contract == Python
#      [PASS] G5 the 4-layer checksum IS forgeable (pins its known weakness)
#      [PASS]   selftest: G2 rejects a deliberately wrong golden vector
#      RESULT: ALL GATES PASS (5/5)
```

Then the individual steps:

```bash
# 0. Independent verifier — no chain, no account needed:
python3 verifier.py "the quick brown fox"
#   -> 338f85c2-a6-3d-09   (this is what the contract returns too)

# 1. Build
asb assembly/index.ts --target release
#   -> build/release/proof-of-delivery.wasm

# 2. Deploy (any funded testnet account you control)
near deploy <your-account>.testnet build/release/proof-of-delivery.wasm \
  --accountId <your-account>.testnet --networkId testnet

# 3. The verified primitive, directly on chain (read-only):
near view <your-account>.testnet commitment '{"payload":"the quick brown fox"}'
#   -> "338f85c2-a6-3d-09"   (identical to step 0 — cross-environment parity)
near view <your-account>.testnet mismatch_count \
  '{"payload":"the quick brownXfox","expectation":"338f85c2-a6-3d-09"}'
#   -> 3        (one character changed; three of the four layers disagree)

# 4. The full escrow round trip, asserted end to end (~90s):
python3 spike_s2_escrow.py
#   -> 11/11 PASS: fund NEAR, deliver, predicate check, release pays the seller,
#      mismatched delivery is rejected, refund after deadline. Real funds move.

# 5. Stablecoins: the same escrow holding a NEP-141 (wNEAR on testnet):
python3 spike_s3_ft_escrow.py
#   -> 10/10 PASS: ft_transfer_call creates the deal, release calls the token's
#      ft_transfer, and the seller's wNEAR grows by exactly the escrowed amount.

# 6. A real FILE, identified by its sha256 (the answer to "how does the buyer
#    know it's the expected file?"):
python3 spike_s4_file_escrow.py
#   -> 10/10 PASS: a 2,078-byte binary file is escrowed by its sha256 and
#      released; a file differing by ONE BYTE is rejected on chain.
sha256sum asset_A.bin        # matches the hash the contract stored

# 7. The settlement state machine (the negative cases the other suites missed):
python3 spike_s5_settlement_guard.py
#   -> 7/7 PASS: repeat release and release-then-refund both revert
#      'deal already settled'; the honest path still pays exactly once.

# 8. Parity, re-runnable (this claim used to be a log line only):
python3 spike_s1_commitment_parity.py
#   -> 20/20 on-chain == Python == browser JS; and it confirms the collision
#      below against the LIVE contract.

# 9. How weak the 4-layer checksum actually is (offline, under a second):
python3 spike_s6_commitment_collision.py
#   -> finds a FULL 4-layer collision in ~37,417 permutations (0.8 s), because
#      three of the four layers are invariant under permutation.

# 10. The agent-economy loop (post -> bid -> award -> deliver -> settle):
python3 spike_s7_two_agent_loop.py
#   -> a buyer agent, two seller agents quoting a price + a content hash, an
#      award, a delivery, a real payout (+0.3770 NEAR), and an adversarial
#      seller who swaps the artifact and is NOT paid (buyer refunded).
```

The on-chain spikes take time and funds. They accept overrides so you can run
them against accounts you control (this is the difference between "read the logs"
and "reproduce it yourself"):

```bash
POD_ESCROW=<your-contract>.testnet POD_BUYER=<your-acct>.testnet \
POD_SELLER=<your-seller>.testnet python3 spike_s2_escrow.py
```

If a key is missing they **abort with a clear message** (exit 2) rather than
blocking on an interactive `near` prompt, and a stalled RPC is reported as a
`TIMEOUT` line instead of crashing the run.

## Why it is different

- **Deterministic release, not a trusted arbiter.** The predicate is recomputed
  on chain from pure integer math; a third party reproduces it offline (proved:
  20/20 byte-identical).
- **Tamper-*detecting*, and honest about its limit.** Four layers, ≥3 break on any
  single-character edit — but L1/L2/L3 are permutation-invariant, so it is a
  corruption detector, **not** a guard against substitution (a full collision
  takes ~2^16 permutations; we demonstrate one). Identity uses sha256.
- **Both failure paths enforced.** A mismatched delivery *reverts*; an
  unsatisfied deal *refunds* (proved on testnet).
- **No instance state, no admin key.** The rule lives entirely in the contract.

## Status / evidence

See [`SPIKE_RESULTS.md`](SPIKE_RESULTS.md) — every number is execution-measured
(build size, deploy tx, 20/20 parity, mutation layer counts, 11/11 escrow steps,
`+1.9998 NEAR` seller balance delta, both reverts).

## Layout

```
assembly/index.ts        the contract (escrow + the commitment primitive)
verifier.py              independent Python reference for the commitment
verify_all.py            one-shot: build + golden + tamper + live-parity gates
demo/index.html          self-contained interactive demo (JS, no chain needed)
spike_s2_escrow.py       native-NEAR escrow round-trip test on testnet
spike_s1_commitment_parity.py  re-runnable 20/20 three-way parity + on-chain forgery check
spike_s6_commitment_collision.py  measures how weak the 4-layer checksum is (finds a collision)
spike_s3_ft_escrow.py    NEP-141 (wNEAR) escrow round-trip test on testnet
spike_s4_file_escrow.py  real FILE escrow by sha256, incl. a 1-byte substitution
spike_s5_settlement_guard.py  settlement state machine: repeat release/refund are rejected
spike_s7_two_agent_loop.py  the agent-economy demo: buyer + 2 sellers, bid → award → settle
exploit_repro_pod3.txt   the measured double-payout output that motivated pod-4
build/release/proof-of-delivery.wasm  committed so code_hash == sha256(wasm) is offline-checkable;
                                  note that the local build hash differs from the
                                  deployed code hash; rebuild and redeploy to match
asset_A.bin, asset_B.bin the two test files (differ by one byte)
SPIKE_RESULTS.md         measured results + the bugs the spikes caught
X_POST_DRAFT.md          demo post + video shot list
```

## License

MIT.
