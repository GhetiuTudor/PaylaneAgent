# Paylane Support Agent — Architecture and Design Guide

## Purpose

This repository is a proof-of-concept customer-support agent for Paylane. It handles refunds, card questions, and cases that must be handed to a human. The LLM handles conversation and tool selection; code owns verification, refund eligibility, and human-only safety decisions.

**Implementation:** `paylane/agent.py` (`Agent` and `Session`), `paylane/policy.py` (`refund_eligibility`), and `paylane/tools.py` (the mock APIs).

> Code computes facts and enforces policy. The model asks questions, selects from safe tools, and writes the customer-facing response.

The distinction is intentional: a system prompt is not a sufficient security boundary for money movement or account privacy.

## Repository map

```text
PaylaneAgent/
├── paylane/
│   ├── agent.py       Conversation loop, system prompt, state machine, dispatcher
│   ├── policy.py      Refund eligibility and date/amount validation
│   ├── tools.py       Four mock APIs and an in-memory store
│   └── llm.py         LLM interface, OpenAI adapter, and deterministic FakeLLM
├── evals/
│   ├── cases.py       Seventeen conversations and independent expectations
│   └── runner.py      Real-model evaluator and transcript writer
├── tests/test_guard.py  Deterministic policy and bypass tests
├── transcripts/       Generated Markdown conversation transcripts
├── chat.py            Interactive command-line demo
├── customer_mail.txt  Plain-language support-lead note
├── README.md          Quick start and production hardening notes
└── ARCHITECTURE.md    This document
```

## Components

| Component | Responsibility | Exact implementation location |
|---|---|---|
| `Agent` | Runs turns, dispatches tools, enforces state and policy boundaries | `paylane/agent.py`: `Agent.run_conversation`, `_run_until_reply`, `_dispatch` |
| `Session` | Holds messages, verification claims, safety state, events, transcript | `paylane/agent.py`: `Session`, `VerificationState`, `SafetyState` |
| `policy.py` | Calculates transaction age and refund eligibility | `paylane/policy.py`: `transaction_age_days`, `refund_eligibility` |
| `tools.py` | Provides mock customer, transaction, refund, and ticket APIs | `paylane/tools.py`: `make_store` and four API functions |
| `OpenAIClient` | Adapts OpenAI chat-completions tool calling | `paylane/llm.py`: `OpenAIClient.chat` |
| `FakeLLM` | Replays exact tool calls for deterministic tests | `paylane/llm.py`: `FakeLLM.chat` |
| `evals/` | Runs realistic conversations and checks expected behaviour | `evals/cases.py`, `evals/runner.py`: `run_checks` |

## Mock APIs

The supplied API contract is implemented as plain Python functions over an in-memory store. Passing the store is only a mock implementation detail.

| Tool | Purpose | Important boundary |
|---|---|---|
| `get_customer(email)` | Looks up the customer and account status | `paylane/tools.py:get_customer`; scrubbed by `paylane/agent.py:_do_get_customer` |
| `get_transaction(customer_id, txn_id)` | Finds an owned transaction | `paylane/tools.py:get_transaction`; gated by `paylane/agent.py:_do_get_transaction` |
| `issue_refund(txn_id, amount)` | Marks a transaction refunded and returns an ID | `paylane/tools.py:issue_refund`; guarded by `paylane/agent.py:_do_issue_refund` |
| `escalate_to_human(customer_id, summary)` | Creates a mock human-support ticket | `paylane/tools.py:escalate_to_human`; state-managed by `paylane/agent.py:_do_escalate` and `_require_human` |

The dictionary store makes tests able to assert whether a refund actually changed a transaction. It is not intended to be a real payment ledger.

**Implementation:** `paylane/tools.py:make_store`; assertions against the store appear throughout `tests/test_guard.py`.

## Architecture and conversation flow

```text
Customer message
      |
      v
Extract email / card-last-four claims
      |
      +--> High-risk detector? -- yes --> Create one ticket
      |                                  Enter human-only state
      |                                  Send fixed safe reply (no LLM call)
      |
      no
      |
      v
LLM tool-calling loop
      |
      +--> get_customer ----> code verifies claims and scrubs secrets
      |                            |
      |                            +--> verified frozen card --> human-only state
      |
      +--> get_transaction -> code calculates age and eligibility fact
      |
      +--> issue_refund ---> deterministic guard ---> mock payment API
      |
      +--> escalate_to_human -> mock ticket
      |
      v
Short, warm customer reply
```

The LLM loop allows at most six model/tool steps for one user turn. This prevents accidental loops. The proof of concept records `(no reply)` if the cap is hit; production code should return a safe fallback response and log an operational error.

**Implementation:** `paylane/agent.py:MAX_STEPS` and `Agent._run_until_reply`. The production fallback is a documented future improvement, not implemented code.

## Verification and privacy

Before discussing account details or acting on an account, the customer must supply both their email on file and their card last-four. `Session.note_claims()` extracts them from customer text. When the LLM calls `get_customer`, `Agent._do_get_customer()` compares those claims against the record. Only code can set `verified=True`.

**Implementation:** `paylane/agent.py:EMAIL_RE`, `LAST4_RE`, `Session.note_claims`, and `Agent._do_get_customer`.

The model gets a reduced result such as:

```json
{"id":"C-A","name":"Customer A","status":"active","verified":true}
```

When verification fails or the email is unknown, the model gets the identical
`{"verified": false}` result. The raw email and card last-four are never included
in tool output, and the prompt forbids repeating them in customer replies.

**Implementation:** `paylane/agent.py:Agent._do_get_customer` creates the reduced result; `paylane/agent.py:SYSTEM_PROMPT` contains the response prohibition; `tests/test_guard.py:test_get_customer_scrubs_secrets_for_model` verifies the tool-result behaviour.

`get_transaction` is blocked before verification. `issue_refund` independently checks verification and transaction ownership, so a direct model call cannot bypass this first gate.

**Implementation:** `paylane/agent.py:Agent._do_get_transaction` and `Agent._do_issue_refund`; covered by `tests/test_guard.py:test_get_transaction_blocked_before_verification`, `test_wrong_last4_is_not_verified`, and `test_guard_blocks_cross_customer_refund`.

Email plus card last-four is appropriate only for this mock. A real product should bind the conversation to an authenticated session or use approved step-up verification such as an OTP.

## Refund policy guard

`paylane/policy.py` determines whether a refund may be auto-approved. Every condition below must be true:

**Implementation:** `paylane/policy.py:refund_eligibility`, called by `paylane/agent.py:Agent._do_get_transaction` and `Agent._do_issue_refund`.

| Check | Behaviour if it fails |
|---|---|
| Customer is verified | `policy.py:refund_eligibility` blocks refund |
| Transaction belongs to the verified customer | `agent.py:_do_issue_refund` blocks refund |
| Transaction is settled | `policy.py:refund_eligibility` blocks and the prompt routes to a human |
| Transaction has not already been refunded | `policy.py:refund_eligibility` blocks duplicate refund |
| Transaction is under 30 days old | `policy.py:transaction_age_days` and `refund_eligibility` block it |
| Original transaction amount is at most $75 | `policy.py:REFUND_LIMIT` and `refund_eligibility` enforce it |
| Requested amount is finite and positive | `policy.py:refund_eligibility` blocks zero, negative, NaN, and infinity |
| Requested amount does not exceed the transaction | `policy.py:refund_eligibility` blocks over-refund |
| Session is not human-only | `agent.py:_do_issue_refund` blocks automated handling |

`get_transaction` adds computed facts before returning data to the LLM:

```json
{
  "amount": 30.0,
  "status": "settled",
  "age_days": 5,
  "auto_approvable": true
}
```

For an ineligible case it returns `auto_approvable: false` and an explanatory reason. That deliberately removes date arithmetic and threshold evaluation from the LLM's job.

**Implementation:** `paylane/agent.py:Agent._do_get_transaction`; the model instruction to consume these values is in `paylane/agent.py:SYSTEM_PROMPT`.

The dispatcher reruns the complete guard against live store data when `issue_refund` is requested. Therefore a hallucinated, injected, or incorrect model tool call cannot bypass verification, age, status, amount, duplicate-refund, ownership, finite-number, or active human-review checks.

**Implementation:** `paylane/agent.py:Agent._do_issue_refund`; adversarial tests are in `tests/test_guard.py`.

### Policy choices and assumptions

- **$75 is inclusive:** “up to $75” includes an exactly-$75 transaction. **Code:** `paylane/policy.py:REFUND_LIMIT` and `refund_eligibility`.
- **Thirty days is exclusive:** “under 30 days” means `age_days < 30`; exactly 30 days escalates. **Code:** `paylane/policy.py:MAX_AGE_DAYS` and `refund_eligibility`.
- **Transaction amount determines the $75 threshold:** a $120 transaction escalates even if the requested refund is $75. **Code:** `paylane/policy.py:refund_eligibility`; the choice is recorded for confirmation in `customer_mail.txt`.
- **Pending transactions are not automatically refunded:** they escalate. **Code:** `paylane/policy.py:refund_eligibility`; the scenario is `evals/cases.py` case 12.
- **Partial refunds are not supported:** the mock records only settled or refunded, so the guard requires the full transaction amount. **Code:** `paylane/policy.py:refund_eligibility`; a durable partial-refund solution is future work.

## Human-only state machine

Some conversations must never return to automated handling, even if the customer changes topic or a model attempts an unsafe later tool call. `SafetyState` is monotonic: once activated, it does not return to normal during the session.

**Implementation:** `paylane/agent.py:SafetyState`, `Agent.run_conversation`, `Agent._require_human`, `Agent._do_get_transaction`, and `Agent._do_issue_refund`.

```text
                 legal / closure / suspected fraud / transfer
                       +------------------------------------+
                       |                                    v
NORMAL ----------------+----------------------------> HUMAN_ONLY
  |                                                        |
  | verified account is frozen                             | later messages
  +--------------------------------------------------------+
                                                           v
                                                safe status reply only
                                                no lookups or refunds
```

### Entry triggers

The state machine enters human-only mode for:

- Legal action.
- Account closure requests.
- Suspected fraud reports.
- Transfer requests, which are out of scope for this proof of concept.
- A frozen card after successful verification.

The brief explicitly calls for escalation for fraud over $500. The first pass conservatively escalates every suspected fraud report because free-form customer text is not an authoritative source for the amount. This decision is also identified for confirmation in `customer_mail.txt`.

**Implementation:** `paylane/agent.py:LEGAL_RE`, `CLOSURE_RE`, `FRAUD_RE`, `TRANSFER_RE`, and `Session.high_risk_reason`; tests are `tests/test_guard.py:test_high_risk_detector_covers_closure_and_fraud`. The authoritative-amount approach is future work only.

### Entry actions

On entry, code:

1. Sets `escalation_required=True` and records the reason.
2. Calls `escalate_to_human` once and stores the ticket ID.
3. Returns a fixed short message saying that support will follow up.
4. Blocks later transaction lookups and refunds in the same session.

The ticket is retained in the transcript even if policy code, rather than an LLM tool call, created it. A later escalation in the same high-risk session returns the existing ticket ID rather than creating another ticket.

**Implementation:** `paylane/agent.py:Agent._require_human`, `_do_escalate`, and `_flush_policy_transcript_events`.

### Why this is necessary

The system prompt tells the model to escalate, but instructions alone do not prevent a later model call to `issue_refund`. The state machine removes that decision from the model for covered high-risk cases. It also makes escalation a real ticket action rather than a sentence that merely claims a human will follow up.

**Implementation:** `paylane/agent.py:Agent.run_conversation` bypasses the model for text triggers, and `Agent._run_until_reply` ends the turn when a lookup activates the state. `tests/test_guard.py:test_frozen_card_creates_ticket_and_blocks_model_refund_attempt` and `test_legal_action_escalates_before_the_model_and_locks_future_turns` prove those paths.

## Detailed request flows

### Eligible refund

1. The customer asks for a refund.
2. The agent asks for verification if claims are missing.
3. The model calls `get_customer`; code verifies the claims.
4. The model asks for the transaction ID if needed.
5. The model calls `get_transaction`; code supplies `age_days` and `auto_approvable`.
6. The model calls `issue_refund` only when eligible.
7. The guard checks again and calls the mock refund API.
8. The model confirms the successful refund in a short response.

**Code path:** `paylane/agent.py:Agent.run_conversation` → `_run_until_reply` → `_dispatch` → `_do_get_customer` → `_do_get_transaction` → `_do_issue_refund` → `paylane/tools.py:issue_refund`.

### Ineligible refund

1. Verification and transaction lookup proceed normally.
2. The transaction result includes `auto_approvable: false` and the reason.
3. The model calls `escalate_to_human` and tells the customer a human will follow up.
4. If the model tries `issue_refund` anyway, the guard blocks it and the mock transaction does not change.

**Code path:** `paylane/agent.py:Agent._do_get_transaction` sets the computed ineligibility fact; `SYSTEM_PROMPT` requests escalation; `Agent._do_issue_refund` is the final enforcement point.

### Legal action, closure, fraud, or transfer

1. The pre-LLM detector finds the trigger in the customer message.
2. Policy code creates a ticket before an account lookup or disclosure.
3. The LLM is skipped for that turn.
4. Later turns remain human-only and cannot resume automated refunds or account handling.

**Code path:** `paylane/agent.py:Session.high_risk_reason` → `Agent.run_conversation` → `_require_human`; the later-turn block is the first branch of `Agent.run_conversation`.

### Frozen card

1. The customer passes verification through `get_customer`.
2. If status is `frozen`, policy code creates a ticket and enters human-only mode.
3. The agent says a specialist will follow up. It cannot unfreeze the card and does not invent a freeze reason.

The mock API supplies no freeze reason. Adding a customer-safe `freeze_reason` is required before the agent can literally explain why a card is frozen.

**Code path:** status is supplied by `paylane/tools.py:get_customer`; the verified-frozen transition is `paylane/agent.py:Agent._do_get_customer`. `freeze_reason` does not exist in the mock API and is a future API change.

## System prompt and LLM role

`SYSTEM_PROMPT` in `paylane/agent.py` defines the conversation style and model orchestration rules:

- Short, warm, plain language without corporate filler.
- Never invent account data or repeat card/email credentials.
- Verify before account details or actions.
- Use the computed eligibility fields instead of doing policy arithmetic.
- Call an escalation tool; do not only narrate an escalation.
- Ask one concise clarifying question for an ambiguous transaction.

The prompt improves the quality of normal conversations. It is not a security boundary; the dispatcher and state machine are.

**Implementation:** `paylane/agent.py:SYSTEM_PROMPT`; enforcement is in `Agent._dispatch`, `_do_get_customer`, `_do_get_transaction`, `_do_issue_refund`, and `_require_human`.

## Evaluation and tests

### Real-model evaluations

`evals/cases.py` defines seventeen hand-written conversations:

| Case | Scenario | Expected behaviour |
|---:|---|---|
| 01 | Exact $75 | Auto-refund |
| 02 | Over $75 | Escalate, no refund |
| 03 | Exactly 30 days old | Escalate, no refund |
| 04 | Already refunded | Never refund twice |
| 05 | Wrong card last-four/social engineering | No disclosure or action |
| 06 | Angry but eligible customer | Warm response and refund |
| 07 | Frozen card | Escalate; do not unfreeze or refund |
| 08 | Ambiguous refund | Ask for transaction ID |
| 09 | Legal action | Immediate escalation |
| 10 | Fraud over $500 | Immediate escalation |
| 11 | Account closure | Immediate escalation |
| 12 | Pending transaction | Conservative escalation |
| 13 | Prompt injection after escalation | No refund; policy cannot be overridden |
| 14 | Fake internal authority | No account access or refund |
| 15 | Split refund on over-limit transaction | Escalate; no refund |
| 16 | Repeated wrong verification | No disclosure or refund |
| 17 | Transfer request | Immediate escalation |

`evals/runner.py` checks required and forbidden calls, refund outcome, escalation, verification gating, and secret leakage in replies. It writes Markdown transcripts to `transcripts/`. The checked-in transcript artifacts report a 12/12 run on `gpt-4o`.

**Implementation:** scenarios are `evals/cases.py:build_cases`; checks are `evals/runner.py:run_checks`; transcript formatting is `evals/runner.py:write_transcript`; the artifacts are `transcripts/*.md`.

The evaluation expectations are deliberately independent of `refund_eligibility()`. A defect in production policy can therefore still fail an evaluation case.

**Implementation:** `evals/cases.py` hard-codes `required_calls`, `forbidden_calls`, and expected outcomes; `evals/runner.py:run_checks` does not import `paylane.policy`.

### Deterministic tests

`tests/test_guard.py` uses `FakeLLM` to script models that ignore instructions and try unsafe tool calls. Coverage includes:

**Implementation:** test fixture helpers are in `tests/test_guard.py`; scripted model responses are from `paylane/llm.py:FakeLLM` and `ToolCall`.

- $75 and 30-day boundaries.
- Pending and already-refunded transactions.
- Zero, negative, and non-finite amounts.
- Failed verification and secret scrubbing.
- Cross-customer transaction IDs and verification reset.
- Frozen-card bypass attempts.
- Legal action followed by a later attempted refund.
- Closure and fraud detector coverage.

## Failure history

An earlier evaluation failed the exactly-30-days case. The model saw a raw ISO date and calculated the boundary incorrectly. The refund guard stopped the money movement, but the customer flow did not escalate as required.

The fix was to compute `age_days` in code and supply `auto_approvable` in the transaction tool result. This is why policy facts are now calculated deterministically rather than delegated to the model.

**Implementation:** `paylane/agent.py:Agent._do_get_transaction`; the regression scenario is `evals/cases.py` case 03 and its transcript is `transcripts/03_exactly_30_days_escalate.md`.

A later safety review identified two guard gaps: a verified frozen customer could reach an eligible refund if the model ignored its prompt, and a NaN amount could evade ordinary numeric comparisons. The state machine and finite-number validation address both paths.

**Implementation:** frozen-card protection is `paylane/agent.py:SafetyState` plus `_do_get_customer`/`_do_issue_refund`; finite validation is `paylane/policy.py:refund_eligibility`; regression tests are `tests/test_guard.py:test_frozen_card_creates_ticket_and_blocks_model_refund_attempt` and `test_guard_blocks_non_finite_amount`.

## Running locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Deterministic tests; no network or API key needed
pytest tests/ -v

# All 17 real-model evaluations; requires an OpenAI key
export OPENAI_API_KEY=sk-...
python -m evals.runner

# Selected evaluation cases
python -m evals.runner --only 05 07

# Interactive demo with preset customers
python chat.py
```

`evals/runner.py` and `chat.py` default to `gpt-4o`; a model can be supplied using `--model`.

**Implementation:** command parsing is in `evals/runner.py:main` and `chat.py:main`; requirements are pinned in `requirements.txt`.

## Production work still required

This is a proof of concept, not a production payment system. Before launch:

- Replace email-plus-last-four with authenticated sessions or step-up verification.
- Replace the regex high-risk detector with a tested decision/classification service and use authorised transaction data for fraud amounts.
- Confirm the policy for fraud under $500, partial refunds, pending charges, frozen-card refunds, refund timing, currencies, and time zones.
- Use integer minor currency units or `Decimal` rather than binary floating point.
- Replace the in-memory store with durable, transactional data and an idempotent payment-provider integration.
- Add durable ticket idempotency, retries, failure handling, audit logs, and approved escalation summaries.
- Redact or encrypt stored messages and transcripts; define retention, deletion, and access controls.
- Add strict API schemas, rate limits, monitoring, alerts, kill switch, rollback, and adversarial tests.
- Add a customer-safe frozen-card reason to the API if Support needs the agent to explain one.

`customer_mail.txt` contains the plain-language launch questions for the head of support.

**Source status:** every item in this section is planned production work rather than implemented code. The current proof-of-concept boundaries are documented in `README.md` and `customer_mail.txt`.
