"""Evaluation harness for the 12 Paylane support-agent conversations.

Modules
-------
cases   — the 12 Case definitions (store seed data, user turns, pass/fail expectations)
runner  — runs cases against a real LLM, applies checks, writes transcripts, prints score
          usage: python -m evals.runner [--model gpt-4o] [--only 05 07]
"""
