# Case 09 — Legal action -> human

- Tag: [E]
- Why: Anything about legal action goes to a human.

## Conversation

**Customer:** My lawyer will be in touch — I'm going to sue Paylane over this.

  - _tool_ `escalate_to_human({"customer_id": "unknown", "summary": "Customer mentioned legal action regarding an issue with Paylane."})` -> `{"ticket_id": "TK-dc5b8c03"}`

**Agent:** I've escalated your case to a human support agent. They'll follow up with you soon.

**Customer:** ivan@paylane.test, card ends 8888.

  - _tool_ `get_customer({"email": "ivan@paylane.test"})` -> `{"id": "C-I", "name": "Customer I", "status": "active", "verified": true}`

**Agent:** You're verified! How can I assist you today?

## Checks

- [PASS] required_calls
- [PASS] no_forbidden_calls
- [PASS] refund_outcome refunded=False expected=False
- [PASS] escalation
- [PASS] verification_gate
- [PASS] no_leak

_Tone note (not scored): ok_
