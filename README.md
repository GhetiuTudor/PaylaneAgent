# Paylane Support Agent

An AI support agent for Paylane cards, transfers, and refunds.
The LLM manages the conversation and selects tools, code owns verification, refund policy, and safety-critical escalation.
It is designed as a take-home assessment, using mock APIs and an in-memory store.

## Architecture

```text
PaylaneAgent/
├── paylane/
│   ├── agent.py       Conversation loop, verification gate, and refund guard
│   ├── policy.py      Refund eligibility rules
│   ├── tools.py       Mock customer, transaction, refund, and ticket APIs
│   └── llm.py         OpenAI adapter and deterministic test double
├── evals/
│   ├── cases.py       Twelve realistic conversations and expected outcomes
│   └── runner.py      Runs real-model evaluations and writes transcripts
├── tests/
│   └── test_guard.py  Deterministic guard and security tests
├── transcripts/       Generated evaluation transcripts
└── chat.py            Interactive CLI
```

## How to run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Deterministic tests; no API key needed
pytest tests/ -v

# Interactive chat or real-model evaluations
export OPENAI_API_KEY=sk-...
python chat.py
python -m evals.runner
```

## Failures I found and fixed

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

## Before production

- Replace email-plus-card-last-four verification with an authenticated session or approved step-up verification flow.
- Use a durable payment ledger and idempotent, atomic refund operations; store provider refund IDs and handle failed or pending provider responses.
- Keep PII out of prompts and transcripts where possible, with appropriate redaction, retention, access control, and audit policies.
- Make escalations durable with retries and idempotency, and return a safe customer fallback when a tool or model call fails.
- Expand automated tests and CI to cover tool failures, malformed upstream data, concurrency, prompt injection, and policy boundaries.
