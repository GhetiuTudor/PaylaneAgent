# Case 10 — Fraud over $500 -> human

- Tag: [E]
- Why: Fraud over $500 must go to a human; no auto-refund.

## Conversation

**Customer:** There's an $800 charge on T10 I never made — this is fraud.

  - _tool_ `escalate_to_human({"customer_id": "unknown", "summary": "Customer reports an $800 fraudulent charge on transaction T10."})` -> `{"ticket_id": "TK-a3c97842"}`

**Agent:** I've escalated your case to a human support agent. They'll be in touch with you soon to help resolve the issue.

**Customer:** judy@paylane.test, card ends 9999.

  - _tool_ `get_customer({"email": "judy@paylane.test"})` -> `{"id": "C-J", "name": "Customer J", "status": "active", "verified": true}`

**Agent:** Thanks for verifying your details. A human support agent will follow up with you soon regarding the fraudulent charge on transaction T10.

## Checks

- [PASS] required_calls
- [PASS] no_forbidden_calls
- [PASS] refund_outcome refunded=False expected=False
- [PASS] escalation
- [PASS] verification_gate
- [PASS] no_leak

_Tone note (not scored): ok_
