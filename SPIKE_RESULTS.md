# Spike results — Proof-of-Delivery escrow

All results below are **measured by execution** against NEAR testnet
(`nft-repo-test-015.testnet`). Nothing here is narrated or estimated.

## Contract

| Fact | Value |
|---|---|
| Toolchain | `near-sdk-as@3.2.3` + `asbuild` (AssemblyScript) |
| Build artifact | `build/release/proof-of-delivery.wasm` — **32,828 B** (`version() == "pod-3"`) |
| Deployed | `nft-repo-test-015.testnet`, tx `4rpJCFKG…`, re-deployed several times during spikes |
| Exports | `version, commitment, check, mismatch_count, sha256_of, create_deal, create_deal_sha, deliver, deliver_bytes, delivery_ok, release, refund, get_deal, ft_on_transfer` |

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

## S4 — escrow a REAL FILE by sha256 identity (binary-safe)

| Step | Result |
|---|---|
| `sha256_of()` on the contract vs Python `hashlib` | **exact match** |
| `create_deal_sha` (buyer commits the file's sha256) | PASS |
| `deliver_bytes` with base64 of a **2,078-byte binary** file | PASS |
| `delivery_ok` → `true` | PASS |
| stored digest == `sha256sum asset_A.bin` | PASS |
| `release` pays the seller | PASS |
| second file, **one byte different**, delivered instead | tx succeeds (the delivery is honest) |
| `delivery_ok` → `false` for the substituted file | PASS |
| `release` **REJECTS** the substituted file | PASS (on-chain revert `delivery does not satisfy the predicate`) |
| `create_deal_sha` rejects a malformed sha256 | PASS (`expected 64 hex chars of sha256`) |

```
VERDICT: VALIDATED — 10/10 steps.
```

`asset_A.bin` and `asset_B.bin` are committed, so a judge can run
`sha256sum asset_A.bin` and compare it to the hash recorded in the run log.

### Correction carried in this file

An earlier note in this session quoted "74.3 bits" for the commitment. That
number belongs to the *bucket signature* measured in a different suite, not to
this predicate. **The 4-layer commitment carries ~52.9 bits**
(32 + log₂231 + log₂231 + log₂37) and FNV-1a is non-cryptographic. It is a
tamper-detection primitive; file identity uses the `sha256:` kind
(256 bits). Recorded here so the wrong number does not propagate.

Bugs the file path surfaced:
- The 4-layer predicate re-used for file identity would have been **wrong**
  (~53 bits, non-cryptographic) — hence the explicit `sha256:` kind.
- A strict tx checker treated the substring `"deadline"` as a revert, but
  near-cli **echoes the scheduled call's arguments**, so every `create_deal*`
  was flagged. Match revert *phrases* (`deadline not reached`), never bare keys.

## Explorer links (all re-queried against the RPC; the last one is a FAILURE by design)

Contract `nft-repo-test-015.testnet`, code_hash `5khSThuj3AYV6dyZeUbzDprKQfY2xSpFJAtBhDNNKMC8`
(= sha256 of the local wasm). Prefix every hash with `https://testnet.nearblocks.io/txns/`.

| step | tx hash |
|---|---|
| deploy pod-3 | `C7iMNjYXdZKpvzJjHSKDcJxmQWr36D3TeUVrRveMcebo` |
| S2 create_deal (2 NEAR) | `5D3sgBtEm3WveXact9pGhWoZJ2JBSnS6VDUvUXLgwQxf` |
| S2 deliver | `FaM3f4nr8EXdxG5qz3vPrc9xihCD9Tuywr132CWMWyks` |
| S2 release → seller | `9pAse5XU2s1Ekn85pz3uMLzHY9ZA8JNqYwX2pr4ZtSzR` |
| S2 refund | `Aw8y9cCf92JcHzhNvWMHQ2BX2aEkWgrDxMdeEBkxft4t` |
| S3 ft_transfer_call | `HmXhLXPAXYFzhjjUDxuRrdfNvJroG88fd2igXTkei3g5` |
| S3 deliver | `ArGfewebuUriV3BopzcqMJQZdxUqTtnzP9hMJETv65RW` |
| S3 release → ft_transfer | `2gfkaT76MkjLurJey6SixDzpYyRRhZXGK2VmMDQmBuNj` |
| S4 create_deal_sha | `5MDpT7kk5yA8CiqKJyESTZH4rcpnhitzQ6XmqaTLdm89` |
| S4 deliver_bytes | `DFnU3j6oSCPJeyw5qdgLTCNaCLQ3boiDD7hzL9TookeZ` |
| S4 release (correct file) | `4Ku5QTBJadTypo44rsmsCHXbAi3ez8cKevw2csvEvJFU` |
| S4 substituted file delivered | `EqSxt4eL6UEPTz3Te5FGBYdFMTRSPRbfPQ4AFh5nPmKW` |
| **S4 release on substituted file → FAILURE** | `Ed4UnTwQAHr5DQGsCSgw8jtg3aSE1bn7TRHh7XEZRnC1` |

## Reproduce

```bash
cd proof-of-delivery
npm install                                      # toolchain (near-sdk-as, asbuild, …)
export PATH="$PWD/node_modules/.bin:$PATH"
asb assembly/index.ts --target release           # -> build/release/proof-of-delivery.wasm
python3 verifier.py "some artifact text"         # independent commitment, no chain needed
python3 verify_all.py --selftest                 # all gates: golden + tamper + live parity
python3 spike_s2_escrow.py                       # full NEAR round trip on testnet (~90s)
python3 spike_s3_ft_escrow.py                    # NEP-141 (wNEAR) round trip on testnet
```

Environment note: the public `rpc.testnet.near.org` endpoint is deprecated and
rate-limits; this box is configured to use `https://rpc.testnet.fastnear.com`
(`~/.config/near-cli/config.toml`).
