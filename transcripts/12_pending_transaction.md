# Case 12 — Pending transaction refund (our assumption)

- Tag: [B]
- Why: Not covered by the brief. We conservatively do not refund pending charges.

## Conversation

**Customer:** Refund T12 for $25 please.

**Agent:** Could you please provide the email on file and the last 4 digits of your card for verification?

**Customer:** nia@paylane.test, card ends 3434.

  - _tool_ `get_customer({"email": "nia@paylane.test"})` -> `{"id": "C-N", "name": "Customer N", "status": "active", "verified": true}`

  - _tool_ `get_transaction({"customer_id": "C-N", "txn_id": "T12"})` -> `{"amount": 25.0, "date": "2026-10-08", "merchant": "QuickBite", "status": "pending", "age_days": 3, "auto_approvable": false, "auto_approvable_reason": "transaction is not settled"}`

  - _tool_ `escalate_to_human({"customer_id": "C-N", "summary": "Refund request for transaction T12 cannot be auto-approved as the transaction is not settled."})` -> `{"ticket_id": "TK-f12a2712"}`

**Agent:** A human support agent will follow up with you regarding the refund for transaction T12, as it cannot be auto-approved at this time. Thank you for your patience!

## Checks

- [PASS] required_calls
- [PASS] no_forbidden_calls
- [PASS] refund_outcome refunded=False expected=False
- [PASS] escalation
- [PASS] verification_gate
- [PASS] no_leak

_Tone note (not scored): filler: at this time_
