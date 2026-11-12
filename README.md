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

## NEAR's role (concrete)

NEAR holds the money and enforces the rule: escrow custody, the seller-only
delivery check, the deterministic predicate evaluation, and the payout/refund
transfer all live in the contract. No backend can switch the release rule off,
and no arbiter is required. This is money that only moves when the *condition*
is met — the programmable-money primitive the track asks for.

## Do X → see Y (a judge can run every line)

**Prereq:** `near` CLI (testnet), `asb`, `python3`. No API keys, no secrets.

```bash
export PATH="<repo>/node_modules/.bin:$HOME/.npm-global/bin:$PATH"

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
demo/index.html          self-contained interactive demo (JS, no chain needed)
spike_s2_escrow.py       native-NEAR escrow round-trip test on testnet
spike_s3_ft_escrow.py    NEP-141 (wNEAR) escrow round-trip test on testnet
SPIKE_RESULTS.md         measured results + the bugs the spikes caught
X_POST_DRAFT.md          demo post + video shot list
```

## License

MIT.
