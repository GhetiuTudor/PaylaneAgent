# Paylane Support Agent (PoC)

A small, readable proof-of-concept support agent for Paylane (cards, transfers,
refunds). It follows the Paylane policy, calls four mock API tools, and is backed
by evals. This is a take-home PoC, not production infrastructure.

## What it does

- Verifies a customer (email on file + last 4 of card) before sharing or acting
  on any account detail.
- Auto-approves refunds **≤ $75** on **settled** transactions **under 30 days**
  old, for **verified** customers, and never refunds the same transaction twice.
- Escalates everything else it shouldn't do itself: refunds over $75 or 30+ days
  old, frozen cards, legal action, fraud over $500, and account closure.
- Never reveals the stored email or card digits.

## What it won't do

- Unfreeze a card, or guess why a card is frozen (the API gives no reason).
- Refund a pending transaction (a conservative assumption — see below).
- Act on account details for anyone who fails verification.

## Layout

```
paylane/
  policy.py   # refund eligibility rules — single source of truth for enforcement
  tools.py    # the 4 mock API tools + in-memory data (only card_last4, no full PAN)
  llm.py      # provider-agnostic client: real OpenAI client + FakeLLM for tests
  agent.py    # system prompt + rulebook, tool-calling loop, verification, refund guard
evals/
  cases.py    # the 12 conversations, each with its own expected outcomes
  runner.py   # runs them on a real LLM, writes transcripts, scores hard/soft checks
tests/
  test_guard.py  # deterministic unit tests (FakeLLM) for the guard + verification gate
transcripts/   # generated per-case transcripts
```

## Policy vs. assumptions vs. safeguards

- **Explicit Paylane policy** is tagged `[E]` in `policy.py` and the rulebook.
- **Conservative assumptions** (tagged `[B]`): $75 inclusive; "under 30 days" so
  exactly 30 escalates; pending not refundable; no over-refund. These are choices
  made where the brief is silent.
- **Engineering safeguards**: the refund guard re-checks policy from live data and
  hard-blocks ineligible refunds even if the model asks; verification is computed
  deterministically in code; the model never receives the email or card digits.

## Run it

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Unit tests (no network, no key needed)
pytest

# The 12 conversations against a real LLM
export OPENAI_API_KEY=sk-...     # set your key in the terminal
python -m evals.runner           # writes transcripts/ and prints a score
python -m evals.runner --only 05 07   # run a subset
python -m evals.runner --model gpt-4o # pick a model
```

The `FakeLLM` is only used by the unit tests. The 12 evaluation conversations run
against the real model.

## Evals

Each case independently declares its expected tool calls and outcome (not computed
from `policy.py`, so a bug in the policy can still fail a case). Hard checks decide
pass/fail: required calls present, forbidden calls absent, refund outcome correct,
verification enforced before account access, and no secret leaked. Tone is a soft,
reported note and never fails a case.
