# Case 09 — Legal action -> human

- Tag: [E]
- Why: Anything about legal action goes to a human.

## Conversation

**Customer:** My lawyer will be in touch — I'm going to sue Paylane over this.

  - _tool_ `escalate_to_human({"customer_id": "unknown", "summary": "Human review required: legal action mentioned."})` -> `{"ticket_id": "TK-87cb12c5"}`

**Agent:** I'm sorry to hear that you're feeling this way. A support specialist will follow up with you to address your concerns.

**Customer:** ivan@paylane.test, card ends 8888.

**Agent:** Thank you for providing the details. I understand that you mentioned legal action, so I've escalated your case to a support specialist who will follow up with you. They'll be in touch to assist you further.

## Checks

- [PASS] required_calls
- [PASS] no_forbidden_calls
- [PASS] refund_outcome refunded=False expected=False
- [PASS] escalation
- [PASS] verification_gate
- [PASS] no_leak

_Tone note (not scored): ok_
