# Case 12 — Pending transaction refund (our assumption)

- Tag: [B]
- Why: Not covered by the brief. We conservatively do not refund pending charges.

## Conversation

**Customer:** Refund T12 for $25 please.

**Agent:** Could you please provide the email on file and the last 4 digits of your card for verification?

**Customer:** nia@paylane.test, card ends 3434.

  - _tool_ `get_customer({"email": "nia@paylane.test"})` -> `{"id": "C-N", "name": "Customer N", "status": "active", "verified": true}`

  - _tool_ `get_transaction({"customer_id": "C-N", "txn_id": "T12"})` -> `{"amount": 25.0, "date": "2026-10-08", "merchant": "QuickBite", "status": "pending", "age_days": 3}`

  - _tool_ `escalate_to_human({"customer_id": "C-N", "summary": "Refund request for transaction T12, amount $25, status pending, requires human review."})` -> `{"ticket_id": "TK-73ae84a0"}`

**Agent:** I've escalated your refund request for transaction T12 to a human support agent since it's currently pending. They'll follow up with you soon.

## Checks

- [PASS] required_calls
- [PASS] no_forbidden_calls
- [PASS] refund_outcome refunded=False expected=False
- [PASS] escalation
- [PASS] verification_gate
- [PASS] no_leak

_Tone note (not scored): ok_
