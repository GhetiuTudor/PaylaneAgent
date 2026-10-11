# Paylane Support Agent

A proof-of-concept AI support agent for Paylane refunds, cards, and transfer queries.
The model manages the conversation, deterministic code owns verification, refund eligibility, and high-risk escalation.
Given the time budget of 4-6h, I focused on what matters the most - agent execution respects policy, deterministic checks and a tool dispatcher for agent reliability, correct behaviour and no user promises.

Tested on:
llama3:8b (served locally) - misses tool calls 50% of the time
gpt-4o-mini - misses tool calls 20% of the time and doesn't always follow the prompt (fake promises)
gpt-4o - correctly calls tools (98% of the times), follows the prompt - chosen for the best balance between cost and performance
gpt-5.6-terra - same performance as 4o but costs $2 for output (which at the scale of Fini clients is a lot)


## How to run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Deterministic safety tests; no API key required
pytest tests/ -v

# Interactive demo and real-model evaluations
export OPENAI_API_KEY=sk-...
python chat.py
python -m evals.runner
```

## Architecture

```text
PaylaneAgent/
├── paylane/
│   ├── agent.py       Conversation loop, verification gate, and policy enforcement
│   ├── policy.py      Refund eligibility rules
│   ├── tools.py       Mock customer, transaction, refund, and ticket APIs
│   └── llm.py         OpenAI adapter and deterministic FakeLLM
├── evals/
│   ├── cases.py       17 real-model evaluation conversations
│   └── runner.py      Evaluates calls, outcomes, leaks, and writes transcripts
├── tests/
│   └── test_guard.py  25 deterministic policy and security tests
├── transcripts/       Evaluation artifacts
├── docs/failure_log.md
├── customer_mail.txt  Policy questions for Paylane Support
└── chat.py            Interactive CLI
```

### Why this architecture holds up

- **Deterministic refund guard:** a model cannot override verification, ownership, amount, age, settlement state, duplicate-refund protection, or human review. The guard rechecks live transaction data immediately before money moves.
- **Monotonic human-only state machine:** legal action, fraud, account closure, transfer requests, and verified frozen cards create exactly one ticket. Later turns cannot return the case to automated account handling or refunding.
- **Privacy boundary at the tool layer:** verification is computed in code, not inferred by the model. Unknown accounts and incorrect credentials return the same model-facing result, preventing account enumeration.
- **Independent evaluation oracle:** expected outcomes are hand-written in `evals/cases.py`, rather than derived from production policy code, so a policy regression can still fail evaluation.

## Key decisions

- **Code, not prompts, is the safety boundary.** Every refund request rereads live transaction data and rechecks verification, ownership, status, age, amount, duplicate-refund state, and human-review state.
- **The model receives computed facts, not arithmetic homework.** Transaction age and `auto_approvable` are calculated in code before the model decides what to say or which safe action to take.
- **Verification is deterministic and privacy-preserving.** Tool output is identical for an unknown email and a wrong card ending: `{"verified": false}`. The model cannot use it to enumerate accounts.
- **High-risk cases bypass the model.** Legal action, fraud, account closure, transfer requests, and verified frozen cards create one ticket and enter a human-only session state.
- **The mock supports full refunds only.** Partial refunds are rejected rather than pretending a binary `settled`/`refunded` record can track a remaining balance. (the mock API has no partialRefund value)

## Ambiguities handled conservatively

The brief leaves several product decisions open. The agent chooses the safer path and records the question for the Head of Support in [`customer_mail.txt`](customer_mail.txt):

- Pending transactions are escalated rather than refunded.
- All suspected fraud is escalated; a customer message is not an authoritative fraud-amount source.
- Frozen cards always go to a human, and the agent does not invent a freeze reason absent from the API.
- Exactly $75 is eligible; a transaction exactly 30 days old is not.
- Verification retry limits and any rolling per-customer refund cap are requested policy decisions, not silently invented thresholds.

## Failures found and fixed

- **30-day boundary:** the model treated an exactly-30-day-old transaction as refundable when it had to infer age from a date string. The guard blocked the refund; `age_days` is now computed in code.
- **Narrated escalation:** the model sometimes promised a human follow-up without calling the escalation tool. The agent now returns `auto_approvable`, and the prompt requires an actual tool call for ineligible refunds.
- **Partial-refund state mismatch:** the mock marked a transaction fully refunded even for a partial amount. The guard now permits only full refunds until a balance-aware ledger exists.
- **Account-enumeration signal:** an unknown email and a wrong card ending previously produced distinguishable tool results. They now produce the same opaque failure result, and failed lookups revoke any prior verified session.

## Before production

- Replace email-plus-card-last-four verification with authenticated sessions or approved step-up verification.
- Use a durable payment ledger with atomic, idempotent refund operations and provider refund-state handling.
- Move escalation to a durable, retryable service with idempotency and customer-safe outage handling.
- Keep PII out of model context and logs where possible; implement retention, access control, and audit requirements.
- Confirm the open policy questions, then add monitoring, red-team evaluation, rate limits, concurrency tests, and a controlled rollout plan.
