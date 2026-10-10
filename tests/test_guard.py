"""deterministic tests for asserting safety """

from __future__ import annotations

from paylane.agent import Agent, Session
from paylane.llm import ChatResult, FakeLLM, ToolCall
from paylane.policy import refund_eligibility
from paylane.tools import make_store


def _store(status="settled", days_ago=5, amount=50.0, last4="4242"):
    return make_store(
        [{"id": "C1", "email": "a@b.test", "name": "A", "card_last4": last4, "status": "active"}],
        [{"txn_id": "T1", "customer_id": "C1", "amount": amount,
          "days_ago": days_ago, "merchant": "M", "status": status}],
    )


def _call(name, **args):
    return ChatResult(tool_calls=[ToolCall(id="x", name=name, arguments=args)])


# --- policy unit tests ------------------------------------------------------

def test_eligibility_happy():
    assert refund_eligibility(verified=True, status="settled", age_days=5,
                              amount=75, txn_amount=75) == (True, "eligible")


def test_eligibility_boundaries():
    assert refund_eligibility(verified=True, status="settled", age_days=30,
                              amount=10, txn_amount=10)[0] is False
    assert refund_eligibility(verified=True, status="settled", age_days=5,
                              amount=75.01, txn_amount=100)[0] is False
    assert refund_eligibility(verified=True, status="pending", age_days=1,
                              amount=10, txn_amount=10)[0] is False
    assert refund_eligibility(verified=True, status="refunded", age_days=1,
                              amount=10, txn_amount=10)[0] is False
    assert refund_eligibility(verified=False, status="settled", age_days=1,
                              amount=10, txn_amount=10)[0] is False


# --- guard blocks ineligible refunds even if the model asks ----------------

def _run_refund(store, claim_email="a@b.test", claim_last4="4242", amount=50.0):
    session = Session(store=store)
    agent = Agent(FakeLLM([
        _call("get_customer", email="a@b.test"),
        _call("issue_refund", txn_id="T1", amount=amount),
        ChatResult(content="done"),
    ]), session)
    agent.run_conversation([f"refund T1, email {claim_email} card ends {claim_last4}"])
    return session


def test_guard_allows_eligible():
    s = _run_refund(_store(amount=75.0), amount=75.0)
    assert any(e.name == "issue_refund" and e.result.get("ok") for e in s.tool_events)
    assert s.store["transactions"]["T1"]["status"] == "refunded"


def test_guard_blocks_over_limit():
    s = _run_refund(_store(amount=200.0), amount=120.0)
    ref = [e for e in s.tool_events if e.name == "issue_refund"][0]
    assert ref.result["ok"] is False and ref.blocked
    assert s.store["transactions"]["T1"]["status"] == "settled"


def test_guard_blocks_old():
    s = _run_refund(_store(days_ago=30), amount=10.0)
    ref = [e for e in s.tool_events if e.name == "issue_refund"][0]
    assert ref.result["ok"] is False


def test_guard_blocks_pending():
    s = _run_refund(_store(status="pending"), amount=10.0)
    ref = [e for e in s.tool_events if e.name == "issue_refund"][0]
    assert ref.result["ok"] is False


def test_guard_blocks_double_refund():
    s = _run_refund(_store(status="refunded"), amount=10.0)
    ref = [e for e in s.tool_events if e.name == "issue_refund"][0]
    assert ref.result["ok"] is False


# --- verification gate ------------------------------------------------------

def test_wrong_last4_is_not_verified():
    s = _run_refund(_store(), claim_last4="0000", amount=10.0)
    assert s.state.verified is False
    ref = [e for e in s.tool_events if e.name == "issue_refund"][0]
    assert ref.result["ok"] is False  # guard blocks unverified refund


def test_get_transaction_blocked_before_verification():
    store = _store()
    session = Session(store=store)
    agent = Agent(FakeLLM([
        _call("get_transaction", customer_id="C1", txn_id="T1"),
        ChatResult(content="need to verify"),
    ]), session)
    agent.run_conversation(["show me T1"])  # no email/last4 provided
    ev = [e for e in session.tool_events if e.name == "get_transaction"][0]
    assert ev.blocked and ev.result.get("error") == "verification_required"


def test_get_customer_scrubs_secrets_for_model():
    store = _store()
    session = Session(store=store)
    agent = Agent(FakeLLM([
        _call("get_customer", email="a@b.test"),
        ChatResult(content="verified"),
    ]), session)
    agent.run_conversation(["email a@b.test card ends 4242"])
    ev = [e for e in session.tool_events if e.name == "get_customer"][0]
    assert ev.result.get("verified") is True
    assert "card_last4" not in ev.result
    assert "email" not in ev.result
