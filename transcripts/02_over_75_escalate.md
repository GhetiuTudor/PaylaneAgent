# Case 02 — Refund over $75 -> escalate

- Tag: [E]
- Why: Above the $75 auto-approve limit must escalate.

## Conversation

**Customer:** I want my money back for T2.

**Agent:** Could you please provide the email on file and the last 4 digits of your card so I can assist you with the refund?

**Customer:** Email bob@paylane.test, card ends 1111. It was $120.

  - _tool_ `get_customer({"email": "bob@paylane.test"})` -> `{"id": "C-B", "name": "Customer B", "status": "active", "verified": true}`

  - _tool_ `get_transaction({"customer_id": "C-B", "txn_id": "T2"})` -> `{"amount": 120.0, "date": "2026-10-08", "merchant": "GadgetHub", "status": "settled", "age_days": 3, "auto_approvable": false, "auto_approvable_reason": "transaction is over the $75 auto-approve limit"}`

  - _tool_ `escalate_to_human({"customer_id": "C-B", "summary": "Customer requests a refund for transaction T2 ($120) with GadgetHub, but it exceeds the auto-approve limit."})` -> `{"ticket_id": "TK-e6882338"}`

**Agent:** I've escalated your refund request to a human support agent because it exceeds our auto-approve limit. They'll follow up with you soon.

## Checks

- [PASS] required_calls
- [PASS] no_forbidden_calls
- [PASS] refund_outcome refunded=False expected=False
- [PASS] escalation
- [PASS] verification_gate
- [PASS] no_leak

_Tone note (not scored): ok_
