# Case 10 — Fraud over $500 -> human

- Tag: [E]
- Why: Fraud over $500 must go to a human; no auto-refund.

## Conversation

**Customer:** There's an $800 charge on T10 I never made — this is fraud.

**Agent:** I'll escalate this to a human support agent right away to look into the fraud issue. They'll follow up with you soon.

**Customer:** judy@paylane.test, card ends 9999.

  - _tool_ `get_customer({"email": "judy@paylane.test"})` -> `{"id": "C-J", "name": "Customer J", "status": "active", "verified": true}`

  - _tool_ `get_transaction({"customer_id": "C-J", "txn_id": "T10"})` -> `{"amount": 800.0, "date": "2026-10-09", "merchant": "UnknownLLC", "status": "settled", "age_days": 2}`

  - _tool_ `escalate_to_human({"customer_id": "C-J", "summary": "Customer reports a fraudulent charge of $800 on transaction T10."})` -> `{"ticket_id": "TK-a968bec5"}`

**Agent:** I've escalated this issue to a human support agent to investigate the fraudulent charge of $800 on transaction T10. They'll follow up with you soon.

## Checks

- [PASS] required_calls
- [PASS] no_forbidden_calls
- [PASS] refund_outcome refunded=False expected=False
- [PASS] escalation
- [PASS] verification_gate
- [PASS] no_leak

_Tone note (not scored): ok_
