# Paylane Support Agent - PoC

AI support agent for Paylane (cards, transfers, refunds). Handles verification,
auto-refunds, and escalation. Built as a take-home assignment.

---

## Architecture

```
paylane/
  policy.py   <- refund eligibility rules
  tools.py    <- 4 mock API functions + in-memory store
  llm.py      <- provider-agnostic client (OpenAIClient + FakeLLM for tests)
  agent.py    <- system prompt, tool loop, verification gate, refund guard

evals/
  cases.py    <- 12 conversations with expected outcomes
  runner.py   <- runs on real LLM, scores, writes transcripts

tests/
  test_guard.py <- deterministic unit tests (no network, no key)

transcripts/  <- generated per-run markdown transcripts
chat.py       <- interactive CLI for manual testing
```

---

## Key architecture decisions

**Deterministic refund guard.** `issue_refund` is wrapped in a code-level check
that re-reads the transaction from the store and re-runs eligibility before
allowing the call through. No unsafe refund can execute regardless of what the model asks for.

**Secrets scrubbed from tool results.** After `get_customer`, the dispatcher strips
`card_last4` and `email` before returning to the model. The model still sees the
customer's original messages (which contain the email and last4 they typed), but
never gets those values confirmed by the API — so it cannot distinguish a valid
credential from a wrong one without the tool result.

**Verification in code, not by the model.** The API always returns `verified: false`.
The dispatcher computes verification itself by comparing the customer's claimed
email and last4 against the record, then passes only `{verified: true/false}` to
the model.

**Computed facts, not model inference.** `get_transaction` appends `age_days`
(computed from the date in code) so the model never has to do date arithmetic.
This directly fixed the one failure found in testing — see below.

**Eval oracle is independent of policy.py.** Each of the 12 cases hardcodes its
expected outcomes. A bug introduced into the production policy logic can still fail
the tests. Score: **12/12 on gpt-4o**.

---

## How to run it

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Unit tests — no network, no key needed
pytest tests/ -v

# 12 eval conversations (requires OPENAI_API_KEY)
export OPENAI_API_KEY=sk-...
python -m evals.runner                    # all 12, gpt-4o
python -m evals.runner --only 05 07      # subset by case ID

# Interactive CLI with preset personas 
python chat.py
```

---

## Failures found and fixed

**Run 1 — Case 03 — 30-day-old transaction, must escalate. FAIL.**

The model attempted `issue_refund` on a charge that was exactly 30 days old and
did not escalate. The refund guard blocked it (`ok: false, age_days >= 30`) — no
money moved — but the behavior was wrong.

**Root cause:** `get_transaction` returned a raw ISO date. The model had to compute
the age itself and got the boundary wrong. LLMs are unreliable at date arithmetic.

**Fix:** The dispatcher now computes `age_days` and appends it to the result.
The system prompt was tightened to use `age_days` directly: `>= 30` is not
eligible, and the model must call `escalate_to_human`, not just say it will.

Eval unchanged. Case 03: PASS.


**Run 2 — Cases 02 and 09 — over-$75 refund and legal action, must escalate. FAIL.**

After the age_days fix, two different cases failed. The model reasoned correctly
(no forbidden calls, no unsafe refund attempted) but narrated the escalation in
text instead of calling `escalate_to_human`. Different cases flaked on each run —
`temperature=0` does not make `gpt-4o-mini` fully deterministic.

**Root cause:** Model reliability. `gpt-4o-mini` is inconsistent on soft escalation
triggers (amount thresholds, legal language), it knows what to do but doesn't
always make the tool call.

**Fix:** Three things: prompt hardening ("escalating means calling the tool - saying
a human will follow up is not enough"), switching the canonical run to `gpt-4o`, and
eliminating model rule evaluation entirely:

- **Before:** The model had to evaluate rules from the system prompt against numerical data -> unreliable.
- **After:** Code computes `auto_approvable: false` and the model just reads a boolean -> deterministic signal.

The model now receives precomputed decision data from `get_transaction`:
```json
{"amount": 30.0, "status": "pending", "age_days": 3, "auto_approvable": false, "auto_approvable_reason": "transaction is not settled"}
```

If `auto_approvable` is false, it escalates immediately.

Safety was never at risk because the refund guard blocked every unsafe call in every run
on every model. This was purely a behavioral/tool-calling reliability issue.

Score after fix: **12/12**.

**Principle:** Code computes facts. The model orchestrates and talks. Safety must
not depend on the model's judgment alone.
