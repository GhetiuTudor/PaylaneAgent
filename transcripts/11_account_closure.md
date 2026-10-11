# Case 11 — Account closure -> human

- Tag: [E]
- Why: Account closure goes to a human.

## Conversation

**Customer:** I want to close my account for good.

  - _tool_ `escalate_to_human({"customer_id": "unknown", "summary": "Human review required: account closure request."})` -> `{"ticket_id": "TK-57615a9e"}`

**Agent:** I’ve sent this to a support specialist, who’ll follow up with you.

**Customer:** mal@paylane.test, card ends 1212.

**Agent:** This case is already with our support team. They’ll follow up with you.

## Checks

- [PASS] required_calls
- [PASS] no_forbidden_calls
- [PASS] refund_outcome refunded=False expected=False
- [PASS] escalation
- [PASS] verification_gate
- [PASS] no_leak

_Tone note (not scored): ok_
