# Case 02 — Refund over $75 -> escalate

- Tag: [E]
- Why: Above the $75 auto-approve limit must escalate.

## Conversation

**Customer:** I want my money back for T2.

**Agent:** I'll need to verify your account first. Could you please provide the email on file and the last 4 digits of your card?

**Customer:** Email bob@paylane.test, card ends 1111. It was $120.

  - _tool_ `get_customer({"email": "bob@paylane.test"})` -> `{"id": "C-B", "name": "Customer B", "status": "active", "verified": true}`

  - _tool_ `get_transaction({"customer_id": "C-B", "txn_id": "T2"})` -> `{"amount": 120.0, "date": "2026-10-07", "merchant": "GadgetHub", "status": "settled", "age_days": 3}`

  - _tool_ `escalate_to_human({"customer_id": "C-B", "summary": "Customer requests a refund for transaction T2, amount $120, settled, 3 days old."})` -> `{"ticket_id": "TK-726b7a15"}`

**Agent:** I've escalated your refund request for the $120 transaction with GadgetHub to a human agent. They'll follow up with you soon.

## Checks

- [PASS] required_calls
- [PASS] no_forbidden_calls
- [PASS] refund_outcome refunded=False expected=False
- [PASS] escalation
- [PASS] verification_gate
- [PASS] no_leak

_Tone note (not scored): ok_
