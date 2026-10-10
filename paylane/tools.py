"""four mock Paylane API tools + an in-memory data store.

Tools are plain functions over a `Store` dict. They return JSON-serialisable
dicts, mirroring the spec. No full card number is ever stored, only `card_last4`.
Verification, scrubbing and the refund guard live in `agent.py`, not here, so this
file stays a mock of the supplied API.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any


def _iso_days_ago(days: int) -> str:
    return (date.today() - timedelta(days=days)).isoformat()


def make_store(customers: list[dict], transactions: list[dict]) -> dict[str, Any]:
    """Build a store from seed rows

    customer row: {email, name, card_last4, status}
    transaction row: {txn_id, customer_id, amount, days_ago, merchant, status}
    """
    return {
        "customers": {c["email"]: dict(c) for c in customers}, #email becomes the lookup key and the value is a separate object 
        "transactions": { t["txn_id"]: {**t, "date": _iso_days_ago(t["days_ago"])} for t in transactions }, #txn_id becomes the key and a separate object + date is the value 
    }


# tools

def get_customer(store: dict, email: str) -> dict:
    c = store["customers"].get(email)
    if not c:
        return {"error": "customer_not_found"}
    return {
        "id": c["id"],
        "name": c["name"],
        "card_last4": c["card_last4"],
        "status": c["status"],
        "verified": False,  #real verification is computed by the agent as per the spec 
    }


def get_transaction(store: dict, customer_id: str, txn_id: str) -> dict:
    t = store["transactions"].get(txn_id)
    if not t or t["customer_id"] != customer_id:
        return {"error": "transaction_not_found"}
    return {
        "amount": t["amount"],
        "date": t["date"],
        "merchant": t["merchant"],
        "status": t["status"],
    }


def issue_refund(store: dict, txn_id: str, amount: float) -> dict:
    t = store["transactions"].get(txn_id)
    if not t:
        return {"ok": False, "reason": "transaction_not_found"}
    if t["status"] == "refunded":
        return {"ok": False, "reason": "already_refunded"}
    t["status"] = "refunded"
    return {"ok": True, "refund_id": f"RF-{uuid.uuid4().hex[:8]}"}


def escalate_to_human(store: dict, customer_id: str, summary: str) -> dict:
    return {"ticket_id": f"TK-{uuid.uuid4().hex[:8]}"}
