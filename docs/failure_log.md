# Failure Log

These failures were found during real-model evaluation and fixed without changing
the evaluation expectations.

## 1. Exact 30-day transaction

The model treated a transaction exactly 30 days old as refundable because it had
to infer the age from an ISO date. The refund guard blocked the action, but the
behaviour was still wrong.

**Fix:** `get_transaction` now returns code-computed `age_days`; `age_days >= 30`
is ineligible and routes to human support.

## 2. Narrated escalation

The model sometimes said a human would follow up without calling
`escalate_to_human`. This appeared on soft escalation triggers such as an
over-limit refund or legal language.

**Fix:** eligibility is now code-computed and returned as `auto_approvable`.
The prompt requires a real escalation tool call whenever it is false.

## Regression coverage

The deterministic suite covers direct unsafe tool calls, cross-customer access,
pushback after a refusal, prompt-injection-style requests, repeated failed
verification, frozen cards, and human-only high-risk sessions.
