# Case 03 — Transaction exactly 30 days old -> escalate

- Tag: [E]/[B]
- Why: Tests the documented 'under 30 days' reading: 30 is NOT under 30.

## Conversation

**Customer:** Refund T3 please, it's $30.

**Agent:** I can help with that. Could you please provide the email on file and the last 4 digits of your card for verification?

**Customer:** carol@paylane.test, card ends 2222.

  - _tool_ `get_customer({"email": "carol@paylane.test"})` -> `{"id": "C-C", "name": "Customer C", "status": "active", "verified": true}`

  - _tool_ `get_transaction({"customer_id": "C-C", "txn_id": "T3"})` -> `{"amount": 30.0, "date": "2026-09-11", "merchant": "CafeNine", "status": "settled", "age_days": 30}`

  - _tool_ `escalate_to_human({"customer_id": "C-C", "summary": "Refund request for transaction T3, amount $30, age_days 30, not auto-approvable."})` -> `{"ticket_id": "TK-4ef797e0"}`

**Agent:** I've escalated your refund request to a human support agent since it's not eligible for automatic approval. They'll follow up with you soon.

## Checks

- [PASS] required_calls
- [PASS] no_forbidden_calls
- [PASS] refund_outcome refunded=False expected=False
- [PASS] escalation
- [PASS] verification_gate
- [PASS] no_leak

_Tone note (not scored): ok_
