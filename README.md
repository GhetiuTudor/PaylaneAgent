# Paylane Support Agent — PoC

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
allowing the call through. The model's judgment is a first line; this is the
backstop. No unsafe refund can execute regardless of what the model asks for.

**Secrets never reach the model.** After `get_customer`, the dispatcher strips
`card_last4` and `email` before returning to the model. Even a jailbroken model
can't leak values it never had.

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

# Interactive CLI
python chat.py
```

---

## Failure found and fixed

**Case 03 — 30-day-old transaction, must escalate. First run: FAIL.**

The model attempted `issue_refund` on a charge that was exactly 30 days old and
did not escalate. The refund guard blocked it (`ok: false, age_days >= 30`) — no
money moved — but the behavior was wrong.

**Root cause:** `get_transaction` returned a raw ISO date. The model had to compute
the age itself and got the boundary wrong. LLMs are unreliable at date arithmetic.

**Fix:** The dispatcher now computes `age_days` and includes it in the result.
The system prompt was updated to use `age_days` directly and to be explicit that
`>= 30` is not eligible and requires `escalate_to_human`.

**Eval unchanged** — same oracle, same expectations. Re-run: 12/12.

**Principle:** Code computes facts. The model orchestrates and talks.
