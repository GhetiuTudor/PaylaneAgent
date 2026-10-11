# Failure Log

These failures were found during real-model evaluation and adversarial review.
The evaluation expectations remain independent of production policy code.

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

**Fix:** eligibility is code-computed. When a verified transaction is old,
over-limit, or pending, the agent creates the ticket in code immediately after
the lookup and enters human-only mode; the model only explains the handoff.

## 3. Ineligible lookup could still rely on the model to hand off

Even after eligibility became a computed fact, an `auto_approvable: false`
result still depended on the model to call `escalate_to_human`. The refund guard
would stop money moving, but a model could reply without a ticket or include a
blocked refund call in the same tool response.

**Fix:** the transaction result now includes `human_review_required`. For a
verified old, over-limit, or pending transaction, the agent invokes the existing
ticket action and enters human-only state in code. The dispatcher stops before
executing later tool calls from that model response. It then gives the model a
separate tool-free handoff turn, with only the stored reason and latest redacted
customer message, so follow-up questions remain natural without reopening
account actions. A regression test proves an attempted refund is not executed.

## Regression coverage

The deterministic suite covers direct unsafe tool calls, cross-customer access,
pushback after a refusal, prompt-injection-style requests, repeated failed
verification, frozen cards, and human-only high-risk sessions.
