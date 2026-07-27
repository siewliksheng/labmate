"""Shared helper for pulling a JSON object out of an LLM response that may
be wrapped in markdown code fences or preceded/followed by stray text.
Raises on failure -- callers decide their own fail-closed fallback, since
what "closed" means differs (guardrails fails to "escalate", a prelab
checklist fails to "fully unresolved").
"""

import json


def extract_json_object(text: str) -> dict:
    start, end = text.index("{"), text.rindex("}") + 1
    return json.loads(text[start:end])
