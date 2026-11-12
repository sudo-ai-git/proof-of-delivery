# Spike results — Proof-of-Delivery escrow

All results below are **measured by execution** against NEAR testnet
(`nft-repo-test-015.testnet`). Nothing here is narrated or estimated.

## Contract

| Fact | Value |
|---|---|
| Toolchain | `near-sdk-as@3.2.3` + `asbuild` (AssemblyScript) |
| Build artifact | `build/release/proof-of-delivery.wasm` — **22,844 B** (`version() == "pod-2"`) |
| Deployed | `nft-repo-test-015.testnet`, tx `4rpJCFKG…`, re-deployed several times during spikes |
| Exports | `commitment, check, mismatch_count, version, create_deal, deliver, delivery_ok, release, refund, get_deal, ft_on_transfer` |

### Three bugs found and fixed by the spikes (each was a real blocker)

1. **`Cannot parse JSON` on every call.** Cause: `@nearBindgen` class state is
   JSON-decoded from storage on every call, and a fresh/reused account has no
   valid state blob. Fix: export **top-level functions**, no instance state.
2. **`commit` / `verify` / `mismatch_layers` never exported.** They silently
   collided with near-sdk-as/AssemblyScript internals — the wasm export section
   simply omitted them (`MethodNotFound` on-chain). Fix: renamed to
   `commitment` / `check` / `mismatch_count`; all now export.
3. **Release rejected a correct delivery.** Cause: the predicate check re-hashed
   the *commitment string* as if it were the payload. Fix: the predicate already
   **is** a commitment, so compare layer-by-layer (`matchingLayers`). Without the
   spike's negative test this would have shipped broken.

## S1 — deterministic predicate (cross-environment + tamper-evidence)

| Check | Result |
|---|---|
| On-chain `commitment(p)` vs independent Python `verifier.commit(p)`, 20 payloads | **20/20 byte-identical** |
| `check(p, commitment(p))` | `true` |
| Layers broken by a single-character mutation (20 mutations) | **min 3, max 4 of 4** (never < 3) |
| Python agrees with the contract on a mutation | `true` |

This retires the reproducibility risk: a judge (or an AI judge) can recompute the
exact same commitment in Python from the README and match the chain.

## S2 — escrow round trip (strict success detection + state polling)

| Step | Result |
|---|---|
| `create_deal` escrows 2 NEAR | PASS (log `deal … funded by …`) |
| deal persisted on chain | PASS (`amount":"2000000000000000000000000"`) |
| `deliver` by the seller | PASS (`delivered … commitment=…`) |
| `delivery_ok` → `true` | PASS |
| `release` pays the seller | PASS (log `released … to nft-repo-loop4.testnet`) |
| seller balance change | **+1.9998 NEAR** (real transfer) |
| deal marked `released` | PASS |
| `delivery_ok` → `false` on a mismatched payload | PASS |
| `release` **REJECTS** a mismatched delivery | PASS (on-chain revert `delivery does not satisfy the predicate`) |
| `refund` BEFORE the deadline | PASS (revert `deadline not reached`) |
| `refund` AFTER the deadline | PASS (log `refunded …`), buyer repaid |

```
VERDICT: VALIDATED — 11/11 steps, strict checks, real funds moved,
reverts enforced on both failure paths.
```

## S3 — NEP-141 (stablecoin) escrow, on the canonical `wrap.testnet`

| Step | Result |
|---|---|
| register buyer / escrow / seller on the FT | PASS |
| buyer wraps NEAR → wNEAR | PASS (`1e24 → 2e24`) |
| `ft_transfer_call` creates the deal in `ft_on_transfer` | PASS |
| deal persisted with `"token":"wrap.testnet"` + amount | PASS |
| seller delivered | PASS |
| `delivery_ok` → `true` | PASS |
| `release` calls the token's `ft_transfer` | PASS |
| seller's wNEAR balance | **+500000000000000000000000 exactly** (the escrowed amount) |

```
VERDICT: VALIDATED — 10/10 steps.
```

Bugs the FT path surfaced (both real, both fixed):
- The FT **rejects self-transfers** (`Sender and receiver should be different`),
  so the buyer account must differ from the escrow contract account.
- The JSON scanners required `"key":"value"` with **no whitespace**; a producer
  emitting `"key": "value"` broke `ft_on_transfer`'s `msg` parse. Now
  whitespace-tolerant and accepts quoted numbers.

## Cross-environment parity — THREE independent implementations

The same payload yields the same commitment from three independent code paths:

| Source | `commitment("the quick brown fox")` |
|---|---|
| on-chain contract (`near view … commitment`) | `338f85c2-a6-3d-09` |
| `verifier.py` (Python) | `338f85c2-a6-3d-09` |
| `demo/index.html` (JavaScript, no chain) | `338f85c2-a6-3d-09` |

**Three-way parity: true.** A judge can verify the predicate without trusting
any of our code.

## Reproduce

```bash
cd /home/sudosudo/proof-of-delivery
export PATH="/home/sudosudo/node_modules/.bin:/home/sudosudo/.npm-global/bin:$PATH"
asb assembly/index.ts --target release          # -> build/release/proof-of-delivery.wasm
python3 verifier.py "some artifact text"         # independent commitment, no chain needed
python3 spike_s2_escrow.py                       # full escrow round trip on testnet (~90s)
```

Environment note: the public `rpc.testnet.near.org` endpoint is deprecated and
rate-limits; this box is configured to use `https://rpc.testnet.fastnear.com`
(`~/.config/near-cli/config.toml`).
