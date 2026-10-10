"""Paylane support-agent package.

Modules
-------
policy  — refund-eligibility rules (single source of truth for production enforcement)
tools   — the four mock API functions + in-memory data store
llm     — provider-agnostic LLM client (OpenAIClient for real runs, FakeLLM for tests)
agent   — tool-calling loop, verification gate, refund guard, session state
"""