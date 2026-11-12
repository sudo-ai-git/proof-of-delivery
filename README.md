# Proof-of-Delivery — escrowed agent payments that release only on verified delivery

**NEAR HACKATHON entry · tracks: `agents`, `security`, `swarms`, `open`**

## The problem (one line)

AI agents can pay each other, but a buyer agent has no way to trust that a
seller agent actually delivered — so agent commerce runs on trust or a human
referee. This contract removes the referee.

## What it is

A **Proof-of-Delivery escrow**: a buyer locks funds — **native NEAR or any
NEP-141 stablecoin** — in a deal with a machine-checkable release predicate.
The seller delivers an artifact. **Any** caller can then trigger `release()`,
and the funds move to the seller *iff* the delivered artifact satisfies the
buyer's predicate — checked deterministically **on chain**. If the deadline
passes with no satisfying delivery, the buyer is refunded.

The predicate is a **4-layer tamper-evident commitment** computed from pure
integer math (no host functions), so it is reproducible byte-for-byte off-chain
by anyone:

```
commitment(payload) = "fnv8-sum2-lin2-odd2"
  L0  FNV-1a-32 over the low byte of each code unit
  L1  sum(byte + index)   mod 231      (231-gate SUM channel)
  L2  sum(byte*22 + index) mod 231     (231-gate LINEAR channel)
  L3  count(odd bytes)   mod 37        (parity channel)
```

A single-character change to the artifact breaks **≥3 of the 4 layers**, so a
tampered delivery cannot satisfy the predicate. `mismatch_count()` reports
*which* layers disagree, not just pass/fail.

**Three independent implementations agree byte-for-byte** — the on-chain
AssemblyScript contract, `verifier.py`, and the JS in `demo/index.html`
(verified: on-chain == Python == JS for the same payloads).

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

> **Honest limit.** The 4-layer commitment carries only **~53 bits** of
> information (32 + log₂231 + log₂231 + log₂37) and FNV-1a is not a
> cryptographic hash. It is a *tamper-detection* primitive — good for showing
> the enforcement mechanism and for detecting accidental corruption — and it
> must **not** gate adversarial file substitution. Use the `sha256:` kind for
> anything a counterparty could profit from swapping.

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

## Verified on NEAR testnet — every transaction

Contract: **`nft-repo-test-015.testnet`** · code_hash **`5khSThuj3AYV6dyZeUbzDprKQfY2xSpFJAtBhDNNKMC8`**
— which is the sha256 of this repo's `build/release/proof-of-delivery.wasm`, so the
deployed code is byte-identical to what you can build here.

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
| `screenshots/09_chain_state.png` | live chain read: `code_hash 5khSThuj…` and the FAILURE/SUCCESS verdict per transaction |
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
```

**Start here — one command runs every gate** (offline + live parity):

```bash
python3 verify_all.py --build --selftest
#   -> [PASS] G1 build (32,828 bytes, key exports present)
#      [PASS] G2 golden vectors           (Python matches values the CONTRACT produced)
#      [PASS] G3 tamper breaks >=3 layers
#      [PASS] G4 live contract == Python
#      [PASS]   selftest: G2 rejects a deliberately wrong golden vector
#      RESULT: ALL GATES PASS (4/4)
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
```

## Why it is different

- **Deterministic release, not a trusted arbiter.** The predicate is recomputed
  on chain from pure integer math; a third party reproduces it offline (proved:
  20/20 byte-identical).
- **Tamper-evident, not just hashed.** Four independent layers, ≥3 break on any
  single-character edit (proved).
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
spike_s3_ft_escrow.py    NEP-141 (wNEAR) escrow round-trip test on testnet
spike_s4_file_escrow.py  real FILE escrow by sha256, incl. a 1-byte substitution
asset_A.bin, asset_B.bin the two test files (differ by one byte)
SPIKE_RESULTS.md         measured results + the bugs the spikes caught
X_POST_DRAFT.md          demo post + video shot list
```

## License

MIT.
