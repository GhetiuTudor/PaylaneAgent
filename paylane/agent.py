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
LAST4_RE = re.compile(r"\b(\d{4})\b")

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
- Never repeat back or reveal the email or the card digits. Do not share account
  details with an unverified customer.

REFUNDS:
- Only act on a refund the customer actually asked for.
- get_transaction returns age_days (how old the charge is in days). Use that
  number directly — do not estimate the age yourself.
- A refund is auto-approvable only when ALL are true: the customer is verified,
  status is settled, age_days is less than 30, the amount is $75 or less, and it
  was not already refunded. age_days of exactly 30 or more is NOT eligible.
- If it is not auto-approvable (over $75, age_days 30 or more, pending, already
  refunded), do NOT call issue_refund. You MUST call escalate_to_human and tell
  the customer a human will follow up.
- Never refund the same transaction twice. If issue_refund returns ok:false, do
  not say the refund went through — escalate instead.

FROZEN CARDS:
- You can tell the customer the card is frozen, but you cannot unfreeze it and you
  do not know why it was frozen. Do not guess a reason. Escalate to a human.

ALWAYS ESCALATE (call escalate_to_human):
- Anything about legal action, fraud over $500, or closing an account.
- Refunds you cannot auto-approve, and frozen cards.
- Escalating means actually calling the escalate_to_human tool. Saying a human
  will follow up is not enough — make the tool call in the same reply, then tell
  the customer.

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
    tool_events: list[ToolEvent] = field(default_factory=list)
    transcript: list[dict] = field(default_factory=list)

    def note_claims(self, text: str) -> None:
        if m := EMAIL_RE.search(text):
            self.state.claimed_email = m.group(0)
        if m := LAST4_RE.search(text):
            self.state.claimed_last4 = m.group(1)


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
                continue
            text = result.content or ""
            self.s.messages.append({"role": "assistant", "content": text})
            self.s.transcript.append({"role": "assistant", "content": text})
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

    # --- dispatch: verification, gating, scrubbing, guard -------------------

    def _dispatch(self, name: str, args: dict[str, Any]) -> dict:
        if name == "get_customer":
            return self._do_get_customer(args.get("email", ""))
        if name == "get_transaction":
            return self._do_get_transaction(args.get("txn_id", ""))
        if name == "issue_refund":
            return self._do_issue_refund(args.get("txn_id", ""), float(args.get("amount", 0)))
        if name == "escalate_to_human":
            return self._do_escalate(args.get("summary", ""))
        return {"error": "unknown_tool"}

    def _do_get_customer(self, email: str) -> dict:
        record = tools.get_customer(self.s.store, email)
        if "error" in record:
            self._log("get_customer", {"email": email}, record)
            return record

        # Deterministic verification: email on file and last4 both match.
        self.s.state.customer_id = record["id"]
        verified = (
            self.s.state.claimed_email is not None
            and self.s.state.claimed_email.lower() == email.lower()
            and self.s.state.claimed_last4 == record["card_last4"]
        )
        if verified:
            self.s.state.verified = True

        # Scrub: never expose email or card_last4, hide details until verified.
        if self.s.state.verified:
            safe = {"id": record["id"], "name": record["name"],
                    "status": record["status"], "verified": True}
        else:
            safe = {"id": record["id"], "verified": False}
        self._log("get_customer", {"email": email}, safe)
        return safe

    def _do_get_transaction(self, txn_id: str) -> dict:
        if not self.s.state.verified:
            out = {"error": "verification_required"}
            self._log("get_transaction", {"txn_id": txn_id}, out, blocked=True)
            return out
        out = tools.get_transaction(self.s.store, self.s.state.customer_id or "", txn_id)
        if "error" not in out:
            out = {**out, "age_days": transaction_age_days(out["date"])}  #improvement 1 - this is why eval 3 failed the first time 
        self._log("get_transaction", {"txn_id": txn_id}, out)
        return out

    def _do_issue_refund(self, txn_id: str, amount: float) -> dict:
        txn = self.s.store["transactions"].get(txn_id)
        if txn is None:
            out = {"ok": False, "reason": "transaction_not_found"}
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
        cid = self.s.state.customer_id or "unknown"
        out = tools.escalate_to_human(self.s.store, cid, summary)
        self._log("escalate_to_human", {"customer_id": cid, "summary": summary}, out)
        return out

    def _log(self, name: str, args: dict, result: dict, blocked: bool = False) -> None:
        self.s.tool_events.append(ToolEvent(name=name, arguments=args, result=result, blocked=blocked))
