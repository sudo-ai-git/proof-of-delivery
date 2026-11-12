# Demo post (final copy — ready to publish)

Per `HACKATHON.md` the **human** publishes this. Required: the post says the
project was built at NEAR HACKATHON, tags **@NEARProtocol** and
**#NEARHackathon** (optionally @NearLegion / @NearBuilders), and attaches the
demo video or screenshots. Lead with the user problem, show one complete moment,
say what NEAR does, give a next step.

Every post below is within X's 280-character limit (URLs counted as 23, per
t.co). Post 1 carries the **video**; posts 2–4 carry **images** in the same
thread (X allows a video *or* images per post, not both).

---

**POST 1** — attach the demo video · **253 chars**

```
Agents can pay each other. They can't verify delivery.

Proof-of-Delivery: escrow that pays a seller only when the delivery is machine-verified on chain.

Change one character and the payout reverts.

Built at NEAR HACKATHON
@NEARProtocol #NEARHackathon
```

**POST 2** — attach the two browser-demo screenshots · **268 chars**

```
The predicate is a 4-layer tamper-evident commitment from pure integer math — no oracle, no host functions.

3 independent implementations agree byte-for-byte: the on-chain contract, a Python verifier, and the browser demo.

One edit breaks at least 3 of the 4 layers.
```

**POST 3** — attach the two terminal-run screenshots · **280 chars**

```
The complete moment, real testnet, real funds:

fund -> deliver -> release pays the seller (+1.9998 NEAR measured)
tampered delivery -> release REVERTS on chain
deadline missed -> buyer refunded

The same escrow holds stablecoins: seller's wNEAR grew by the exact escrowed amount.
```

**POST 4** — attach the `verify_all` terminal screenshot · **242 chars**

```
Contract + an independent verifier you can run yourself: https://github.com/sudo-ai-git/proof-of-delivery

One command: python3 verify_all.py --build --selftest

What would you use verifiable delivery for first — data, compute, or API access?
```

---

## Video shot list (~60–75s, one take is fine)

1. **(0–8s) Problem.** "Agents can pay each other. They can't verify delivery."
2. **(8–20s) The primitive, no chain.** `python3 verifier.py "agent deliverable v1"` → the commitment; then one character changed and `mismatch_count` → 3. Say: "four independent layers; one edit breaks at least three."
3. **(20–45s) The complete moment.** `python3 spike_s2_escrow.py` — narrate the PASS lines: fund → deliver → **release pays the seller** (the seller's NEAR ticks +2), then the mismatched delivery and the on-chain **revert**.
4. **(45–60s) Stablecoins.** `python3 spike_s3_ft_escrow.py` — the seller's wNEAR grows by exactly the escrowed amount.
5. **(60–75s) Ask.** Show the repo, state NEAR's role (custody, seller-only delivery, on-chain predicate, settlement), ask the closing question.

Screenshots fallback (if no video): the `01/02` browser pair, the `04` escrow
run, and the `03` `verify_all` output.
