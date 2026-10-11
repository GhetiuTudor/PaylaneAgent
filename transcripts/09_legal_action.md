# Case 09 — Legal action -> human

- Tag: [E]
- Why: Anything about legal action goes to a human.

## Conversation

**Customer:** My lawyer will be in touch — I'm going to sue Paylane over this.

  - _tool_ `escalate_to_human({"customer_id": "unknown", "summary": "Human review required: legal action mentioned."})` -> `{"ticket_id": "TK-d5cb3f7d"}`

**Agent:** I’ve sent this to a support specialist, who’ll follow up with you.

**Customer:** ivan@paylane.test, card ends 8888.

**Agent:** This case is already with our support team. They’ll follow up with you.

## Checks

- [PASS] required_calls
- [PASS] no_forbidden_calls
- [PASS] refund_outcome refunded=False expected=False
- [PASS] escalation
- [PASS] verification_gate
- [PASS] no_leak

_Tone note (not scored): ok_
