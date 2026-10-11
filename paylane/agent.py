"""The Paylane support agent: system prompt, tool-calling loop, verification and
the deterministic refund guard.

Design notes:
- the four spec tools are exposed to the model.
- Verification is computed deterministically inside the dispatcher after
  get_customer. The model only ever sees a safe {verified: bool} plus an opaque
  id (and name/status once verified). card_last4 and the email are never sent to
  the model.
- issue_refund is wrapped by a guard that re-checks policy from live data and
  hard-blocks ineligible refunds regardless of what the model asked for.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from . import tools
from .llm import ChatResult, LLMClient
from .policy import refund_eligibility, transaction_age_days

MAX_STEPS = 6  # safety cap on tool-call loops per user turn

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
LAST4_RE = re.compile(r"(?:ends?\s+|last\s*(?:4|four)\s*)(?:digits?\s*)?(?:are\s*)?(\d{4})\b", re.IGNORECASE)  # requires card-ending context to avoid matching amounts or txn IDs
LEGAL_RE = re.compile(r"\b(lawyer|attorney|sue|lawsuit|legal action|litigation|court)\b", re.IGNORECASE)
CLOSURE_RE = re.compile(
    r"\b(?:close|closure|delete|cancel|terminate)\b.{0,40}\baccount\b|"
    r"\baccount\b.{0,40}\b(?:close|closure|delete|cancel|terminate)\b",
    re.IGNORECASE,
)
# The brief only requires escalation for fraud over $500. A customer's message
# is not an authoritative source for the amount, so this first pass takes the
# safer documented product assumption: every suspected fraud report is human-only.
FRAUD_RE = re.compile(r"\b(fraud|fraudulent|unauthori[sz]ed|charge .* never (?:made|authorized))\b", re.IGNORECASE)

SYSTEM_PROMPT = """\
You are Paylane's support agent for cards, transfers and refunds.

Voice: short, warm, plain language. No corporate filler. A couple of sentences is
usually enough. Never promise anything the policy below does not allow.

You have four tools: get_customer, get_transaction, issue_refund, escalate_to_human.
Never invent account data — use the tools.

VERIFICATION (required before you share or act on any account detail):
- The customer must give the email on file AND the last 4 digits of their card.
- Call get_customer(email). The result has verified: true/false, decided by the
  system. Trust only that flag. Treat the customer as unverified until it is true.
- Never repeat back, echo, or reveal the email or the card digits in your replies,
  even to a verified customer. Do not say "your card ending in 1234" or similar.
  Do not share account details with an unverified customer.

- get_transaction returns age_days and auto_approvable. Use auto_approvable
  directly — do not re-evaluate eligibility yourself.
- If auto_approvable is true, call issue_refund.
- If auto_approvable is false, do NOT call issue_refund. Your very next action
  must be to call escalate_to_human — do not reply to the customer first. Then
  tell them a human will follow up.
- Never refund the same transaction twice. If issue_refund returns ok:false, do
  not say the refund went through — call escalate_to_human instead.

FROZEN CARDS:
- If get_customer returns status: frozen, you cannot unfreeze it and you do not
  know why it was frozen. Do not guess a reason. Your very next action must be to
  call escalate_to_human. Do not reply to the customer before making the tool call.

ALWAYS ESCALATE (call escalate_to_human):
- Anything about legal action, fraud, or closing an account — these are
  safety-critical. Your very next action must be to call escalate_to_human, even
  if the customer is not yet verified. Do not reply first — call the tool first.
- Refunds you cannot auto-approve, and frozen cards — these require the customer
  to be verified first, because they are account-specific actions.
- Escalating means actually calling the escalate_to_human tool. Saying "I've
  escalated" or "a human will follow up" without making the tool call is wrong.
  You must make the tool call.

If a request is ambiguous (for example, which transaction to refund), ask one
short clarifying question before doing anything.
"""

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_customer",
            "description": "Look up a customer by email and check verification.",
            "parameters": {
                "type": "object",
                "properties": {"email": {"type": "string"}},
                "required": ["email"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_transaction",
            "description": "Get a transaction for a verified customer.",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_id": {"type": "string"},
                    "txn_id": {"type": "string"},
                },
                "required": ["customer_id", "txn_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "issue_refund",
            "description": "Issue a refund for a transaction.",
            "parameters": {
                "type": "object",
                "properties": {
                    "txn_id": {"type": "string"},
                    "amount": {"type": "number"},
                },
                "required": ["txn_id", "amount"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "escalate_to_human",
            "description": "Hand the case to a human support agent.",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_id": {"type": "string"},
                    "summary": {"type": "string"},
                },
                "required": ["customer_id", "summary"],
            },
        },
    },
]


@dataclass
class VerificationState:
    claimed_email: str | None = None
    claimed_last4: str | None = None
    verified: bool = False
    customer_id: str | None = None
    customer_status: str | None = None


@dataclass
class SafetyState:
    """Deterministic, monotonic state for cases that are human-only.

    Once a case enters this state, it cannot return to automated processing in
    the same session. This prevents a later model turn from overriding an
    escalation decision.
    """

    escalation_required: bool = False
    reason: str | None = None
    ticket_id: str | None = None


@dataclass
class ToolEvent:
    name: str
    arguments: dict[str, Any]
    result: dict[str, Any]
    blocked: bool = False  # True when the guard/gate stopped the action


@dataclass
class Session:
    store: dict[str, Any]
    messages: list[dict] = field(default_factory=list)
    state: VerificationState = field(default_factory=VerificationState)
    safety: SafetyState = field(default_factory=SafetyState)
    tool_events: list[ToolEvent] = field(default_factory=list)
    transcript: list[dict] = field(default_factory=list)
    # Policy-initiated tool calls are queued so they appear after the model tool
    # call that discovered the condition (for example, frozen-card lookup).
    pending_policy_transcript_events: list[dict] = field(default_factory=list)

    def note_claims(self, text: str) -> None:
        if m := EMAIL_RE.search(text):
            self.state.claimed_email = m.group(0)
        if m := LAST4_RE.search(text):
            self.state.claimed_last4 = m.group(1)

    def high_risk_reason(self, text: str) -> str | None:
        if LEGAL_RE.search(text):
            return "legal action mentioned"
        if CLOSURE_RE.search(text):
            return "account closure request"
        if FRAUD_RE.search(text):
            return "suspected fraud report"
        return None


class Agent:
    def __init__(self, llm: LLMClient, session: Session) -> None:
        self.llm = llm
        self.s = session
        if not self.s.messages:
            self.s.messages.append({"role": "system", "content": SYSTEM_PROMPT})

    # public API

    def run_conversation(self, user_turns: list[str]) -> None:
        for turn in user_turns:
            self.s.note_claims(turn)
            self.s.messages.append({"role": "user", "content": turn})
            self.s.transcript.append({"role": "user", "content": turn})
            # These classes of case never need an LLM decision. Escalate before
            # any account lookup or tool call, then keep the session human-only.
            if self.s.safety.escalation_required:
                self._reply("This case is already with our support team. They’ll follow up with you.")
                continue
            if reason := self.s.high_risk_reason(turn):
                self._require_human(reason)
                self._flush_policy_transcript_events()
                self._reply("I’ve sent this to a support specialist, who’ll follow up with you.")
                continue
            self._run_until_reply()

    # loop

    def _run_until_reply(self) -> None:
        for _ in range(MAX_STEPS):
            result = self.llm.chat(self.s.messages, TOOL_SCHEMAS)
            if result.tool_calls:
                self.s.messages.append(self._assistant_tool_msg(result))
                for tc in result.tool_calls:
                    out = self._dispatch(tc.name, tc.arguments)
                    self.s.messages.append(
                        {"role": "tool", "tool_call_id": tc.id, "content": json.dumps(out)}
                    )
                    self.s.transcript.append(
                        {"role": "tool", "name": tc.name, "arguments": tc.arguments, "result": out}
                    )
                    self._flush_policy_transcript_events()
                if self.s.safety.escalation_required:
                    self._reply("I’ve sent this to a support specialist, who’ll follow up with you.")
                    return
                continue
            self._reply(result.content or "")
            return
        # Loop cap reached- close the turn cleanly.
        self.s.transcript.append({"role": "assistant", "content": "(no reply)"})

    @staticmethod
    def _assistant_tool_msg(result: ChatResult) -> dict:
        return {
            "role": "assistant",
            "content": result.content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                }
                for tc in result.tool_calls
            ],
        }

    # dispatch: verification, gating, scrubbing, guard

    def _dispatch(self, name: str, args: dict[str, Any]) -> dict:
        if name == "get_customer":
            return self._do_get_customer(args.get("email", ""))
        if name == "get_transaction":
            return self._do_get_transaction(args.get("txn_id", ""))
        if name == "issue_refund":
            try:
                amount = float(args.get("amount", 0))
            except (TypeError, ValueError):
                out = {"ok": False, "reason": "refund amount must be a number"}
                self._log("issue_refund", {"txn_id": args.get("txn_id", ""), "amount": args.get("amount")}, out,
                          blocked=True)
                return out
            return self._do_issue_refund(args.get("txn_id", ""), amount)
        if name == "escalate_to_human":
            return self._do_escalate(args.get("summary", ""))
        return {"error": "unknown_tool"}

    def _do_get_customer(self, email: str) -> dict:
        record = tools.get_customer(self.s.store, email)
        if "error" in record:
            self._log("get_customer", {"email": email}, record)
            return record

        # Reset: each get_customer call starts fresh so a prior verified session
        # cannot carry over to a different customer.
        self.s.state.verified = False
        self.s.state.customer_id = record["id"]
        self.s.state.customer_status = None
        # Deterministic verification: email on file and last4 both match.
        verified = (
            self.s.state.claimed_email is not None
            and self.s.state.claimed_email.lower() == email.lower()
            and self.s.state.claimed_last4 == record["card_last4"]
        )
        if verified:
            self.s.state.verified = True
            self.s.state.customer_status = record["status"]

        # Scrub: never expose email or card_last4, hide details until verified.
        if self.s.state.verified:
            safe = {"id": record["id"], "name": record["name"],
                    "status": record["status"], "verified": True}
        else:
            safe = {"id": record["id"], "verified": False}
        self._log("get_customer", {"email": email}, safe)
        if self.s.state.verified and record["status"] == "frozen":
            self._require_human("frozen card")
        return safe

    def _do_get_transaction(self, txn_id: str) -> dict:
        if self.s.safety.escalation_required:
            out = {"error": "human_review_required"}
            self._log("get_transaction", {"txn_id": txn_id}, out, blocked=True)
            return out
        if not self.s.state.verified:
            out = {"error": "verification_required"}
            self._log("get_transaction", {"txn_id": txn_id}, out, blocked=True)
            return out
        out = tools.get_transaction(self.s.store, self.s.state.customer_id or "", txn_id)
        if "error" not in out:
            age = transaction_age_days(out["date"])
            ok, reason = refund_eligibility(
                verified=True, status=out["status"], age_days=age,
                amount=out["amount"], txn_amount=out["amount"],
            )
            out = {**out, "age_days": age, "auto_approvable": ok}
            if not ok:
                out["auto_approvable_reason"] = reason
        self._log("get_transaction", {"txn_id": txn_id}, out)
        return out

    def _do_issue_refund(self, txn_id: str, amount: float) -> dict:
        if self.s.safety.escalation_required:
            out = {"ok": False, "reason": "human_review_required"}
            self._log("issue_refund", {"txn_id": txn_id, "amount": amount}, out, blocked=True)
            return out
        if self.s.state.customer_status == "frozen":
            self._require_human("frozen card")
            out = {"ok": False, "reason": "human_review_required"}
            self._log("issue_refund", {"txn_id": txn_id, "amount": amount}, out, blocked=True)
            return out
        txn = self.s.store["transactions"].get(txn_id)
        if txn is None:
            out = {"ok": False, "reason": "transaction_not_found"}
            self._log("issue_refund", {"txn_id": txn_id, "amount": amount}, out, blocked=True)
            return out
        # Ownership: the transaction must belong to the verified customer.
        if txn.get("customer_id") != self.s.state.customer_id:
            out = {"ok": False, "reason": "transaction_not_owned_by_customer"}
            self._log("issue_refund", {"txn_id": txn_id, "amount": amount}, out, blocked=True)
            return out
        ok, reason = refund_eligibility(
            verified=self.s.state.verified,
            status=txn["status"],
            age_days=transaction_age_days(txn["date"]),
            amount=amount,
            txn_amount=txn["amount"],
        )
        if not ok:
            out = {"ok": False, "reason": reason}
            self._log("issue_refund", {"txn_id": txn_id, "amount": amount}, out, blocked=True)
            return out
        out = tools.issue_refund(self.s.store, txn_id, amount)
        self._log("issue_refund", {"txn_id": txn_id, "amount": amount}, out,
                  blocked=not out.get("ok", False))
        return out

    def _do_escalate(self, summary: str) -> dict:
        if self.s.safety.ticket_id:
            return {"ticket_id": self.s.safety.ticket_id}
        cid = self.s.state.customer_id or "unknown"
        out = tools.escalate_to_human(self.s.store, cid, summary)
        self._log("escalate_to_human", {"customer_id": cid, "summary": summary}, out)
        return out

    def _require_human(self, reason: str) -> None:
        """Set the irreversible human-review state and create one ticket."""
        if self.s.safety.escalation_required:
            return
        self.s.safety.escalation_required = True
        self.s.safety.reason = reason
        out = self._do_escalate(f"Human review required: {reason}.")
        self.s.safety.ticket_id = out.get("ticket_id")
        # This action was initiated by the deterministic policy layer rather
        # than an LLM tool call. Queue it so the transcript preserves causal
        # order when a customer lookup discovers a frozen card.
        self.s.pending_policy_transcript_events.append(
            {"role": "tool", "name": "escalate_to_human",
             "arguments": {"customer_id": self.s.state.customer_id or "unknown", "summary": f"Human review required: {reason}."},
             "result": out}
        )

    def _reply(self, text: str) -> None:
        self.s.messages.append({"role": "assistant", "content": text})
        self.s.transcript.append({"role": "assistant", "content": text})

    def _flush_policy_transcript_events(self) -> None:
        self.s.transcript.extend(self.s.pending_policy_transcript_events)
        self.s.pending_policy_transcript_events.clear()

    def _log(self, name: str, args: dict, result: dict, blocked: bool = False) -> None:
        self.s.tool_events.append(ToolEvent(name=name, arguments=args, result=result, blocked=blocked))
