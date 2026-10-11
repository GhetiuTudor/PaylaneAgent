# Case 08 — Ambiguous refund -> clarifying question

- Tag: trap
- Why: Two eligible transactions; agent must ask which one before refunding.

## Conversation

**Customer:** Please refund my payment.

**Agent:** Could you please provide the email on file and the last 4 digits of your card? Once I have that information, I'll be able to assist you further.

**Customer:** heidi@paylane.test, card ends 7777.

  - _tool_ `get_customer({"email": "heidi@paylane.test"})` -> `{"id": "C-H", "name": "Customer H", "status": "active", "verified": true}`

**Agent:** Could you please provide the transaction ID for the payment you'd like refunded? This will help me locate the specific transaction.

## Checks

- [PASS] required_calls
- [PASS] no_forbidden_calls
- [PASS] refund_outcome refunded=False expected=False
- [PASS] clarifying_question
- [PASS] verification_gate
- [PASS] no_leak

_Tone note (not scored): ok_
