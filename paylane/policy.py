"""Paylane refund policy - the single source of truth for production enforcement

Tags in comments mark where each clause comes from:
  [E] explicit Paylane policy (from the email)
  [B] conservative assumption I chose, to be checked after the response from Deep

This module is used by the agent's refund guard. It is deliberately not used by
the eval harness as its oracle: eval cases state their own expected outcomes so a
bug introduced here can still fail the tests.
"""

from __future__ import annotations

import math
from datetime import date

REFUND_LIMIT = 75.0   # [E] auto-approve "up to $75" -> inclusive
MAX_AGE_DAYS = 30     # [E] must be "under 30 days"; [B] exactly 30 is NOT under 30


def transaction_age_days(txn_date: str, today: date | None = None) -> int:
    """days between the transaction date and today."""
    today = today or date.today()
    return (today - date.fromisoformat(txn_date)).days


def refund_eligibility(
    *,
    verified: bool,
    status: str,
    age_days: int,
    amount: float,
    txn_amount: float,
) -> tuple[bool, str]:
    """Return (ok, reason). ok=True only when a refund may be auto-approved."""
    # Tool arguments are untrusted, even if a model schema says "number". In
    # particular, comparisons with NaN are always false, so it must be rejected
    # explicitly before the amount comparisons below.
    if not math.isfinite(amount) or not math.isfinite(txn_amount):
        return False, "refund amount must be a finite number"
    if not verified:
        return False, "customer is not verified"    # [E] verify before account action
    if status == "refunded":
        return False, "transaction already refunded"  # [E] never refund twice
    if status != "settled":
        return False, "transaction is not settled"   # [B] pending/other not refundable
    if age_days >= MAX_AGE_DAYS:
        return False, "transaction is 30 days or older"   # [E] older than 30 days -> escalate
    if amount <= 0:
        return False, "refund amount must be positive"  # [B] reject zero/negative
    if txn_amount > REFUND_LIMIT:
        return False, "transaction is over the $75 auto-approve limit"  # [E] above $75 -> escalate
    if amount > txn_amount:
        return False, "refund exceeds the transaction amount"  # [B] no over-refund
    return True, "eligible"
