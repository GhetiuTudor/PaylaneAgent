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

---

## Hardenings I would implement before production deployment

This is a take-home proof of concept. Before handling real customers or moving
money, I would complete the following work.

### Make every policy action enforceable in code

- Add a per-conversation policy state machine. Once legal action, account
  closure, a qualifying fraud report, or a frozen card is detected, block
  `issue_refund` and account-detail tools as appropriate, create/confirm the
  human ticket, and prevent the model from overriding that state.
- Determine fraud amount from an authorised transaction lookup rather than
  trusting a number in the message. Define the safe behaviour while the amount
  or transaction is unknown (conservatively, escalate).
- Do not create unauthenticated account-specific tickets with customer ID
  `unknown`. Decide whether an unverified legal report should create a generic,
  rate-limited intake ticket or first request verification; then implement that
  decision consistently.
- Make escalation reliable: use an idempotency key, durable queue/retries and
  explicit error handling. Tell the customer a ticket exists only after the
  escalation service confirms it, provide a safe fallback if the tool or the
  model loop fails.

### Finish the money-movement contract

- Confirm whether the $75 threshold applies to the original transaction, the
  refund amount, or both. The current implementation deliberately uses the
  original transaction amount, record that decision in the product policy.
- Define full versus partial refunds. Either require `amount == transaction
  amount`, or store refunded and remaining amounts and make partial refunds
  atomic. The mock currently marks a transaction simply `refunded`, so it
  cannot represent a partial refund correctly.
- Validate amounts in integer minor currency units (not binary floats), require
  a finite positive value, verify the currency, and reject malformed numeric
  values such as `NaN`. Obtain transaction amounts, dates and status from the
  payment ledger only.
- Replace the in-memory store with a transactional, durable backend. Make
  refund creation idempotent and atomic so concurrent requests cannot both pass
  the “not already refunded” check. Persist the provider refund ID and handle
  pending, failed, reversed and duplicate provider responses.
- Use an agreed Paylane timezone and authoritative timestamps for the 30-day
  calculation. Define handling for future dates, clock skew, daylight-saving
  changes, and the exact 30-day boundary.

### Strengthen identity, privacy and tool boundaries

- Email plus card last four is only a mock verification mechanism, not strong
  customer authentication. In production, bind the conversation to an
  authenticated session or use a step-up verification flow such as OTP.
- Keep credentials and PII out of the model context where feasible. Capture
  verification fields in a secure UI/service, pass opaque verification state to
  the model, and avoid placing them in model tool-call arguments.
- Redact or encrypt customer messages, tool arguments and transcripts. The
  sample tool results are scrubbed, but raw user messages and transcript logs
  can still contain email and card-last-four data. Define access controls,
  retention, deletion and audit requirements before launch.
- Validate every tool argument server-side with strict schemas and
  authorisation checks. Maintain ownership checks, reject unknown/malformed
  identifiers, constrain summaries, and protect tool services against prompt
  injection, replay and excessive ticket creation.
- Add a customer-safe frozen-card reason to the API if Support expects the
  agent to explain it. (I chose not to infer it now)

### Resolve product-policy gaps before launch

- Get written decisions for pending transactions, fraud at or below $500,
  frozen-card refunds, partial refunds, supported currencies, refund timing and
  the $75/30-day boundary semantics. Encode those choices in both the policy
  guard and customer-facing wording.
- Define what the agent may say or do for customer-not-found, transaction-not-
  found, verification failure, unsupported requests, and upstream outages.
- Add an approved escalation summary format that shares the minimum necessary
  information with Support and gives agents enough context to act.

### Prove reliability continuously

- Expand deterministic tests to cover bypass attempts: legal/fraud/closure
  language combined with an otherwise eligible refund, frozen-card flows,
  unauthenticated escalation, partial/zero/negative/non-finite amounts,
  cross-customer IDs, tool failures and concurrent duplicate refunds.
- Strengthen eval assertions. A clarifying-question check should validate that
  the question actually identifies the missing transaction, and required tool
  calls should include the transaction lookup whenever eligibility depends on
  transaction data.
- Run version-pinned, repeatable model evaluations in CI across multiple runs;
  retain the model/version, prompts and anonymised artifacts. Treat a
  temperature of zero as a configuration, not a guarantee of determinism.
- Add pre-launch monitoring: policy-block and escalation metrics, refund/ticket
  error rates, sampled quality review, red-team prompt-injection testing,
  alerts, a kill switch and a rollback plan. Launch with limited traffic and
  human review until those controls are proven.
