"""Interactive CLI chat with the Paylane"""

from __future__ import annotations

import argparse
import os

from paylane.agent import Agent, Session
from paylane.llm import OpenAIClient
from paylane.tools import make_store

CUSTOMERS = [
    {"id": "C-ALICE", "email": "alice@paylane.test", "name": "Alice", "card_last4": "4242", "status": "active"},
    {"id": "C-BOB", "email": "bob@paylane.test", "name": "Bob", "card_last4": "1111", "status": "active"},
    {"id": "C-GRACE", "email": "grace@paylane.test", "name": "Grace", "card_last4": "6666", "status": "frozen"},
    {"id": "C-NIA", "email": "nia@paylane.test", "name": "Nia", "card_last4": "3434", "status": "active"},
]

TRANSACTIONS = [
    {"txn_id": "T100", "customer_id": "C-ALICE", "amount": 40.0, "days_ago": 5, "merchant": "BrightMart", "status": "settled"},
    {"txn_id": "T101", "customer_id": "C-ALICE", "amount": 90.0, "days_ago": 10, "merchant": "GadgetHub", "status": "settled"},
    {"txn_id": "T200", "customer_id": "C-BOB", "amount": 20.0, "days_ago": 45, "merchant": "BookNest", "status": "settled"},
    {"txn_id": "T300", "customer_id": "C-NIA", "amount": 25.0, "days_ago": 3, "merchant": "QuickBite", "status": "pending"},
]

PERSONAS = """\
Test personas (give the agent the email + last 4 to verify):
  Alice  alice@paylane.test  last4 4242  -> T100 $40 settled 5d (refundable),
                                            T101 $90 settled 10d (over $75)
  Bob    bob@paylane.test    last4 1111  -> T200 $20 settled 45d (too old)
  Grace  grace@paylane.test  last4 6666  -> card FROZEN
  Nia    nia@paylane.test    last4 3434  -> T300 $25 PENDING
  --------------------------------------------------------------------------
  Welcome to Paylane customer support. I am an AI Agent, how can I help you?
Type 'quit' to exit.
"""


def _print_new(session: Session, start: int) -> None:
    for item in session.transcript[start:]:
        if item["role"] == "tool":
            print(f"    · {item['name']}({item['arguments']}) -> {item['result']}")
        elif item["role"] == "assistant":
            print(f"Agent: {item['content']}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gpt-4o")
    args = ap.parse_args()

    if not os.environ.get("OPENAI_API_KEY"):
        print("OPENAI_API_KEY is not set.")
        return 2

    session = Session(store=make_store(CUSTOMERS, TRANSACTIONS))
    agent = Agent(OpenAIClient(model=args.model), session)

    print(PERSONAS)
    while True:
        try:
            line = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if line.lower() in {"quit", "exit"}:
            break
        start = len(session.transcript)
        agent.run_conversation([line])
        _print_new(session, start)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
