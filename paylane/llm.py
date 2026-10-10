"""Provider agnostic LLM client

- `LLMClient` is the interface the agent depends on
- `OpenAIClient` is the one real provider (used for the 12 eval conversations)
- `FakeLLM` is a deterministic scripted client for unit testing
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass # OpenAI already provides an object for this, but this makes it provider-agnostic - can be tested with any LLM 
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ChatResult:
    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)


class LLMClient(Protocol):
    def chat(self, messages: list[dict], tools: list[dict]) -> ChatResult: ...


class OpenAIClient:
    """Real provider. Reads the key from OPENAI_API_KEY"""

    def __init__(self, model: str = "gpt-4o-mini") -> None:
        from openai import OpenAI  # imported lazily so that this file can be loaded at test time with no SDK dependency 

        self.model = model
        self._client = OpenAI()

    def chat(self, messages: list[dict], tools: list[dict]) -> ChatResult:
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=tools,
            temperature=0,
        )
        msg = resp.choices[0].message
        calls = [
            ToolCall(id=tc.id, name=tc.function.name, arguments=json.loads(tc.function.arguments or "{}"))
            for tc in (msg.tool_calls or [])
        ]
        return ChatResult(content=msg.content, tool_calls=calls)


class FakeLLM:
    """Deterministic client that replays a scripted list of ChatResults.

    Unit tests only.
    """

    def __init__(self, script: list[ChatResult]) -> None:
        self._script = list(script)
        self._i = 0

    def chat(self, messages: list[dict], tools: list[dict]) -> ChatResult:
        result = self._script[self._i]
        self._i += 1
        return result
