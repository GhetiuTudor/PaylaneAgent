# Case 12 — Pending transaction refund (our assumption)

- Tag: [B]
- Why: Not covered by the brief. We conservatively do not refund pending charges.

## Conversation

**Customer:** Refund T12 for $25 please.

**Agent:** Could you please provide the email on file and the last 4 digits of your card for verification?

**Customer:** nia@paylane.test, card ends 3434.

  - _tool_ `get_customer({"email": "nia@paylane.test"})` -> `{"id": "C-N", "name": "Customer N", "status": "active", "verified": true}`

  - _tool_ `get_transaction({"customer_id": "C-N", "txn_id": "T12"})` -> `{"amount": 25.0, "date": "2026-10-07", "merchant": "QuickBite", "status": "pending", "age_days": 3}`

**Agent:** The transaction is still pending, so I can't process the refund automatically. I'll escalate this to a human agent who will follow up with you.

## Checks

- [PASS] required_calls
- [PASS] no_forbidden_calls
- [PASS] refund_outcome refunded=False expected=False
- [PASS] verification_gate
- [PASS] no_leak

_Tone note (not scored): ok_
