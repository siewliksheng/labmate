"""M3: the enforced safety escalation gate.

Wraps every specialist's completed draft response, not only the safety
specialist's -- a hazard can hide in a literature summary or a vision
description just as easily as in an explicit safety question (see
docs/architecture.md, "no specialist ever clears a hazard on its own").

Two independent checks; either flagging a hazard is enough to escalate,
both must clear for a response to pass:

1. Deterministic checks (no LLM call, cannot be reasoned around):
   - Any tool result this turn came back `found: false` (unresolved) and
     the specialist did NOT call escalate_to_safety_officer afterward.
     "Not found" is never read as "not hazardous" -- see gap #4 in
     docs/architecture.md.
   - A hazard keyword appears in the draft response text itself.
2. LLM groundedness check (labmate.llm_client, so it works against a
   local Ollama model or Claude): a separate call reviewing whether every
   claim in the draft is backed by a source actually retrieved this turn.
   Runs via labmate.llm_client, which is pluggable -- see its module
   docstring for the local-vs-Claude tradeoff. Fails CLOSED to escalate
   on any error (network, parsing, no backend configured) -- "you are
   required to justify clearance," per docs/system_prompts.md.

Known limitation, not hidden: the deterministic hazard-keyword check is a
small hardcoded list (see _HAZARD_KEYWORDS below), not a hazard-entity
lookup -- it can miss a genuinely novel, unnamed hazard that the LLM
groundedness check also doesn't happen to flag. This is exactly why M6
adds a dedicated cross-specialist reviewer on top of what's here, not a
claim that this gate is already complete.
"""

import json

from labmate.json_utils import extract_json_object
from labmate.llm_client import create_message
from labmate.mcp_server.tools import dispatch_tool

# Deliberately the same crude, hardcoded shape as orchestrator.py's
# SAFETY_KEYWORDS -- applied here to OUTPUT text instead of the user's
# input. A model can be argued with; a substring match cannot.
_HAZARD_KEYWORDS = ("safe", "danger", "hazard", "toxic", "dispose", "expose", "harm", "fine to", "should be okay")

_GATE_EVALUATOR_SYSTEM_PROMPT = """\
You are the safety gate for LabMate. You review a draft response before \
it reaches a lab member. You do not rewrite or improve the draft -- you \
decide whether it may be released as-is, or must be blocked and \
escalated to a human safety officer instead.

You will be given the original user request, which specialist produced \
the draft, the tools that specialist actually called this turn and what \
they returned, and the draft response itself.

Escalate -- do not release -- if ANY of the following is true:
1. The draft makes a claim about safety, hazard level, or an action \
being permissible, that is not directly backed by one of the retrieved \
tool results listed. Training knowledge alone is never sufficient.
2. A substance, organism, procedure, or piece of equipment mentioned has \
no matching entry among the retrieved tool results. Treat "not found" as \
unresolved, not as "not hazardous."
3. You are genuinely uncertain for any reason not listed above. Default \
to escalate. You are not required to justify caution; you are required \
to justify clearance.

Only if every factual claim in the draft traces to a retrieved tool \
result, and none of the above apply, may you clear the draft for release.

Respond with ONLY strict JSON, no other text:
{"verdict": "clear" or "escalate", "reasoning": "<one sentence>"}
"""


def enforce_safety_gate(specialist_name: str, user_input: str, tool_call_log: list[dict], draft_text: str) -> dict:
    if _already_escalated(tool_call_log):
        return _clear(draft_text, "specialist already escalated via escalate_to_safety_officer")

    unresolved = _unresolved_lookups(tool_call_log)
    if unresolved:
        names = [call["name"] for call in unresolved]
        return _force_escalate(
            specialist_name, user_input, tool_call_log, draft_text, reasoning=f"unresolved lookup(s): {names}"
        )

    deterministic_flag = _contains_hazard_signal(draft_text)
    llm_verdict = llm_groundedness_check(user_input, specialist_name, tool_call_log, draft_text)

    if deterministic_flag or llm_verdict["verdict"] == "escalate":
        reasoning = llm_verdict.get("reasoning") or "deterministic hazard-keyword match in the draft response"
        return _force_escalate(specialist_name, user_input, tool_call_log, draft_text, reasoning=reasoning)

    return _clear(draft_text, "deterministic check and LLM groundedness check both cleared")


def llm_groundedness_check(user_input: str, specialist_name: str, tool_call_log: list[dict], draft_text: str) -> dict:
    try:
        sources_summary = (
            "\n".join(
                f"- {call['name']}({call['input']}) -> {json.dumps(call['result'])[:500]}" for call in tool_call_log
            )
            or "(no tools were called)"
        )
        prompt = (
            f"Original request: {user_input}\n\n"
            f"Specialist: {specialist_name}\n\n"
            f"Retrieved tool results this turn:\n{sources_summary}\n\n"
            f"Draft response to review:\n{draft_text}"
        )
        response = create_message(
            system=_GATE_EVALUATOR_SYSTEM_PROMPT, messages=[{"role": "user", "content": prompt}], max_tokens=256
        )
        text = "".join(block.text for block in response.content if getattr(block, "type", None) == "text")
        return _parse_verdict(text)
    except Exception as exc:
        return {"verdict": "escalate", "reasoning": f"groundedness check itself failed ({exc}) -- fail closed"}


def _parse_verdict(text: str) -> dict:
    try:
        parsed = extract_json_object(text)
        if parsed.get("verdict") not in {"clear", "escalate"}:
            raise ValueError(f"unexpected verdict value: {parsed.get('verdict')!r}")
        return parsed
    except Exception as exc:
        return {"verdict": "escalate", "reasoning": f"could not parse evaluator response ({exc}) -- fail closed"}


def _already_escalated(tool_call_log: list[dict]) -> bool:
    return any(
        call["name"] == "escalate_to_safety_officer" and isinstance(call["result"], dict) and call["result"].get("escalated")
        for call in tool_call_log
    )


def _unresolved_lookups(tool_call_log: list[dict]) -> list[dict]:
    return [call for call in tool_call_log if isinstance(call["result"], dict) and call["result"].get("found") is False]


def _contains_hazard_signal(text: str) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in _HAZARD_KEYWORDS)


def _force_escalate(specialist_name: str, user_input: str, tool_call_log: list[dict], draft_text: str, reasoning: str) -> dict:
    summary = (
        f"[{specialist_name}] {user_input}\n\nGate reasoning: {reasoning}\n\nBlocked draft response:\n{draft_text}"
    )
    escalate_result = dispatch_tool("escalate_to_safety_officer", {"summary": summary, "urgency": "urgent"})
    return {
        "verdict": "escalate",
        "response_text": (
            "This question has been escalated to a human safety officer rather than answered directly. "
            f"(Queued at {escalate_result.get('queued_at', 'unknown time')}.)"
        ),
        "reasoning": reasoning,
    }


def _clear(draft_text: str, reasoning: str) -> dict:
    return {"verdict": "clear", "response_text": draft_text, "reasoning": reasoning}
