"""A minimal pluggable LLM backend.

Exists so this project's tool-calling loop and M3's gate logic can be
exercised for $0 against a local Ollama model, without touching agent.py,
tools.py, or the specialists at all -- LLM_BACKEND=ollama (see
.env.example) is the only thing that changes. Both backends return the
same block shape (objects with .type in {"text", "tool_use"}, tool_use
blocks carrying .id/.name/.input) so the rest of the codebase never
branches on which backend is active.

Honest tradeoff, not hidden: a small local model is real for exercising
harness mechanics (routing, tool-calling, the gate's deterministic checks),
but this project's actual safety-reasoning quality is only as good as the
model making the groundedness judgment call. Claude Sonnet 5 remains the
documented target for anything beyond local development -- see README
"Stack".

Not wired into analyze_image's vision calls -- translating Anthropic's
image content-block format to Ollama's vision format is real work with an
unproven payoff (Ollama vision models are markedly weaker at the kind of
hazard-scan reasoning this project needs), so it's left out rather than
half-done. Text-only tool-calling is the actual value here.
"""

import json
import os
from types import SimpleNamespace

import httpx
from anthropic import Anthropic


def create_message(system: str, messages: list, tools: list | None = None, max_tokens: int = 2048):
    backend = os.environ.get("LLM_BACKEND", "anthropic")
    if backend == "ollama":
        return _create_message_ollama(system, messages, tools, max_tokens)
    return _create_message_anthropic(system, messages, tools, max_tokens)


def _create_message_anthropic(system, messages, tools, max_tokens):
    client = Anthropic()
    kwargs = {"model": "claude-sonnet-5", "max_tokens": max_tokens, "system": system, "messages": messages}
    if tools:
        kwargs["tools"] = tools
    return client.messages.create(**kwargs)


def _to_openai_tools(tools: list) -> list:
    return [
        {
            "type": "function",
            "function": {"name": t["name"], "description": t["description"], "parameters": t["input_schema"]},
        }
        for t in tools
    ]


def _block_attr(block, name, default=None):
    """Blocks may be real Anthropic SDK objects or our own SimpleNamespace
    stand-ins from a prior Ollama turn -- both are duck-typed the same way.
    """
    return getattr(block, name, None) if not isinstance(block, dict) else block.get(name, default)


def _to_openai_messages(system: str, messages: list) -> list:
    openai_messages = [{"role": "system", "content": system}]

    for msg in messages:
        role, content = msg["role"], msg["content"]

        if isinstance(content, str):
            openai_messages.append({"role": role, "content": content})
            continue

        if role == "assistant":
            text_parts = []
            tool_calls = []
            for block in content:
                block_type = _block_attr(block, "type")
                if block_type == "text":
                    text_parts.append(_block_attr(block, "text", ""))
                elif block_type == "tool_use":
                    tool_calls.append(
                        {
                            "id": _block_attr(block, "id"),
                            "type": "function",
                            "function": {
                                "name": _block_attr(block, "name"),
                                "arguments": json.dumps(_block_attr(block, "input")),
                            },
                        }
                    )
            openai_messages.append(
                {"role": "assistant", "content": "\n".join(text_parts) or None, "tool_calls": tool_calls or None}
            )
        else:
            # user role holding a list of tool_result dicts from the loop
            for block in content:
                openai_messages.append({"role": "tool", "tool_call_id": block["tool_use_id"], "content": block["content"]})

    return openai_messages


def _create_message_ollama(system, messages, tools, max_tokens):
    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    model = os.environ.get("OLLAMA_MODEL", "llama3.1")

    payload = {"model": model, "messages": _to_openai_messages(system, messages), "stream": False}
    if tools:
        payload["tools"] = _to_openai_tools(tools)

    resp = httpx.post(f"{host}/v1/chat/completions", json=payload, timeout=120)
    resp.raise_for_status()
    message = resp.json()["choices"][0]["message"]

    blocks = []
    if message.get("content"):
        blocks.append(SimpleNamespace(type="text", text=message["content"]))
    for call in message.get("tool_calls") or []:
        blocks.append(
            SimpleNamespace(
                type="tool_use",
                id=call["id"],
                name=call["function"]["name"],
                input=json.loads(call["function"]["arguments"]),
            )
        )

    stop_reason = "tool_use" if message.get("tool_calls") else "end_turn"
    return SimpleNamespace(content=blocks, stop_reason=stop_reason)
