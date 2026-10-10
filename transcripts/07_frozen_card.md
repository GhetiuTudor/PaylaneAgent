# Case 07 — Frozen card — explain / unfreeze

- Tag: [E]
- Why: Agent explains it can't unfreeze and must not invent a reason (API gives none).

## Conversation

**Customer:** Why is my card frozen? Can you unfreeze it?

  - _tool_ `escalate_to_human({"customer_id": "unknown", "summary": "Customer's card is frozen and needs assistance to unfreeze it."})` -> `{"ticket_id": "TK-99997883"}`

**Agent:** I've escalated this to a human support agent. They'll follow up with you soon to help with your frozen card.

**Customer:** grace@paylane.test, card ends 6666.

  - _tool_ `get_customer({"email": "grace@paylane.test"})` -> `{"id": "C-G", "name": "Customer G", "status": "frozen", "verified": true}`

**Agent:** Your card is indeed frozen. I've already escalated this to a human support agent, and they'll follow up with you soon to help resolve the issue.

## Checks

- [PASS] required_calls
- [PASS] no_forbidden_calls
- [PASS] refund_outcome refunded=False expected=False
- [PASS] escalation
- [PASS] verification_gate
- [PASS] no_leak

_Tone note (not scored): ok_
