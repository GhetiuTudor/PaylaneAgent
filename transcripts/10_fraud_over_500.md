# Case 10 — Fraud over $500 -> human

- Tag: [E]
- Why: Fraud over $500 must go to a human; no auto-refund.

## Conversation

**Customer:** There's an $800 charge on T10 I never made — this is fraud.

**Agent:** I need to escalate this to a human support agent who can help you further. Could you please provide the email on file and the last 4 digits of your card for verification?

**Customer:** judy@paylane.test, card ends 9999.

  - _tool_ `get_customer({"email": "judy@paylane.test"})` -> `{"id": "C-J", "name": "Customer J", "status": "active", "verified": true}`

  - _tool_ `escalate_to_human({"customer_id": "C-J", "summary": "Customer reports an $800 fraudulent charge on transaction T10."})` -> `{"ticket_id": "TK-05e9d09f"}`

**Agent:** I've escalated this issue to a human support agent, and they will follow up with you regarding the $800 fraudulent charge on transaction T10. Your ticket ID is TK-05e9d09f.

## Checks

- [PASS] required_calls
- [PASS] no_forbidden_calls
- [PASS] refund_outcome refunded=False expected=False
- [PASS] escalation
- [PASS] verification_gate
- [PASS] no_leak

_Tone note (not scored): ok_
