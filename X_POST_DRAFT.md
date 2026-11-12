# Demo post draft (for X)

Per HACKATHON.md the human publishes this. Required: the post says the project
was built at NEAR HACKATHON, tags **@NEARProtocol** and **#NEARHackathon**
(optionally @NearLegion / @NearBuilders), and attaches the demo video or
screenshots. Lead with the user problem; show one complete moment; say what NEAR
does; give a next step.

---

## Post text (primary — video attached)

> AI agents can already pay each other. The problem is the other half: a buyer agent has no way to know the seller actually *delivered*. So agent commerce falls back on trust, or a human referee. 🧵
>
> We built **Proof-of-Delivery** at NEAR HACKATHON — escrow that releases agents' money only when delivery is *machine-verified*.
>
> How it works: the buyer locks funds (NEAR or any stablecoin) against a predicate that is a 4-layer tamper-evident commitment of the expected artifact. The seller delivers. Then **anyone** can call `release()`, and the contract recomputes the commitment from the delivered payload — on chain — and pays the seller only if every layer matches.
>
> One edited character breaks ≥3 of the 4 layers, so a swapped or tampered deliverable simply does not pay out. No arbiter. No backend anyone can switch off.
>
> In the demo: fund → deliver → release pays the seller; then the same flow with one character changed — and the release **reverts** on chain. Refund after the deadline works too.
>
> NEAR is doing the part that makes this possible: custodying the funds, enforcing seller-only delivery, evaluating the predicate deterministically, and settling the payout. That's programmable money with a *condition* attached.
>
> Everything is open: contract + an independent Python verifier you can run against the chain yourself (20/20 commitments matched byte-for-byte).
>
> Repo: <REPO_URL>
> What would you use verifiable delivery for first — data, compute, or API access? 👇
>
> Built at NEAR HACKATHON · @NEARProtocol · #NEARHackathon

---

## Shorter variant

> Built **Proof-of-Delivery** at NEAR HACKATHON: escrow for AI agents that releases funds only when the delivered artifact is machine-verified on chain.
>
> Buyer locks funds → seller delivers → the contract recomputes a 4-layer tamper-evident commitment and pays out only on an exact match. Change one character and the release **reverts**; miss the deadline and the buyer is refunded. No arbiter, no off-switch. NEAR holds the money and enforces the rule.
>
> Contract + independent Python verifier in the repo: <REPO_URL>
>
> @NEARProtocol #NEARHackathon

---

## Demo video shot list (~60–75s, one take is fine)

1. **(0–8s) Problem.** Screen: the one-liner on an otherwise empty slide — "agents can pay; they can't verify delivery."
2. **(8–20s) The primitive, no chain yet.** Terminal: `python3 verifier.py "agent deliverable v1"` → prints `xxxx-xx-xx-xx`. Then the same string with one character changed and `mismatch_count` → `3`. Say: "four independent layers; one edit breaks three."
3. **(20–45s) The complete moment.** Terminal: `python3 spike_s2_escrow.py` — narrate the PASS lines as they scroll: fund → deliver → **release pays the seller** (and the seller's NEAR balance ticks +2) → then the mismatched delivery and the on-chain **revert** (`delivery does not satisfy the predicate`).
4. **(45–60s) Stablecoins.** `python3 spike_s3_ft_escrow.py` → seller's wNEAR balance grows by exactly the escrowed amount.
5. **(60–75s) Ask.** Show the repo, state the NEAR role, ask the question from the post.

Screenshots fallback (if no video): one image of the S2 run's PASS block, one of the revert line, one of the S1 parity output.
