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
   - analyze_image's hazard-scan pass returned non-empty findings.
     docs/architecture.md gap #5 said this should route to the gate as
     "hazard signal present" from M1 -- that promise wasn't actually
     wired in until M5's eval suite exercised it and found the gap.
   - A hazard keyword appears in the draft response text itself
     (_HAZARD_PATTERN below).
2. LLM groundedness check (labmate.llm_client, so it works against a
   local Ollama model or Claude): a separate call reviewing the draft
   against what was actually retrieved this turn. Runs via
   labmate.llm_client, which is pluggable -- see its module docstring for
   the local-vs-Claude tradeoff. Fails CLOSED to escalate on any error
   (network, parsing, no backend configured) -- "you are required to
   justify clearance," per docs/system_prompts.md.

   The rules it applies are SPECIALIST-AWARE (_gate_prompt_for): strict
   full-groundedness for the safety specialist, narrower
   "did this stray into ungrounded safety territory" rules for
   literature/vision. The gate still runs on every specialist -- that
   part is non-negotiable -- but asking "does every research fact have an
   SDS entry behind it" of a literature answer escalated essentially
   everything, including drafts that made no safety claim at all. See
   docs/architecture.md.

Known limitation, not hidden: the deterministic hazard-keyword check is a
small hardcoded pattern (_HAZARD_PATTERN below), not a hazard-entity
lookup -- it can miss a genuinely novel, unnamed hazard that the LLM
groundedness check also doesn't happen to flag. This is exactly why M6
adds a dedicated cross-specialist reviewer on top of what's here, not a
claim that this gate is already complete.
"""

import json
import re

from labmate.json_utils import extract_json_object
from labmate.llm_client import create_message
from labmate.mcp_server.tools import dispatch_tool

# Same crude, hardcoded spirit as orchestrator.py's SAFETY_KEYWORDS, but
# applied to OUTPUT text instead of the user's input. A model can be
# argued with; a regex cannot.
#
# Word-boundary matched, with variants spelled out explicitly, after
# naive substring matching was found to fire on "p(harm)aceutical" and
# "(safe)ty" -- which would escalate essentially every pharma or
# lab-safety-adjacent literature answer. Variants are listed rather than
# stemmed so each one is a deliberate choice: "harmless" IS included,
# since downplaying a hazard is exactly what this net should catch.
_HAZARD_PATTERN = re.compile(
    r"\b("
    r"safe|safely|unsafe"
    r"|danger|dangers|dangerous"
    # "biohazard"/"biohazardous" spelled out: the eval suite caught the
    # word-boundary change silently dropping the formaldehyde-spill
    # scenario, which the old substring match had been catching via
    # "bio(hazard)". Compound words need to be listed, not assumed.
    r"|hazard|hazards|hazardous|biohazard|biohazards|biohazardous"
    r"|toxic|toxicity|nontoxic|non-toxic"
    r"|dispose|disposal|disposing"
    r"|expose|exposed|exposure"
    r"|harm|harmful|harmless"
    # Reassurance phrasing -- the shape of a draft waving away a concern.
    r"|fine to|should be fine|should be okay|perfectly fine|no big deal"
    r")\b",
    re.IGNORECASE,
)

# The strict rules -- correct for a draft that IS a safety verdict, where
# "every claim traces to a retrieved source" is exactly the bar.
_SAFETY_GATE_RULES = """\
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
"""

# Narrower rules for literature/vision drafts. The gate still runs on
# every specialist -- a hazard CAN hide in a literature summary, which is
# the whole reason for that design (docs/architecture.md) -- but the
# question being asked has to be the right one. Applying the safety rules
# above to a research answer escalated essentially everything: a draft
# saying "I couldn't find specifics, here are three related papers"
# makes no safety claim at all, yet got flagged for "claiming an optimal
# temperature without a matching SDS entry." What matters for these
# specialists is whether the draft strays into safety territory
# ungrounded, not whether every research fact has an SDS entry behind it.
_NON_SAFETY_GATE_RULES = """\
This draft came from a research/observation specialist, not the safety \
specialist. It is NOT expected to be a safety assessment, and ordinary \
research content does not need a safety source behind it.

Escalate -- do not release -- if ANY of the following is true:
1. The draft asserts that something is safe, harmless, permissible, or \
low-risk, without a retrieved tool result directly supporting that.
2. The draft recommends or endorses a specific physical action with \
plausible injury, exposure, contamination, or disposal risk.
3. The draft downplays, dismisses, or explains away a hazard, an \
unresolved lookup, or a flagged finding.
4. The draft mentions a substance, organism, or procedure in a way that \
implies it has been safety-checked when it has not.

Otherwise -- including when the draft simply reports findings, \
summarizes papers, describes an image, or says it could not find \
something -- clear it. Reporting a lack of information is not a safety \
claim. Discussing experimental parameters (temperatures, times, \
concentrations) as reported in the literature is not a safety claim \
unless the draft asserts they are safe to use.
"""

_GATE_EVALUATOR_SYSTEM_PROMPT = """\
You are the safety gate for LabMate. You review a draft response before \
it reaches a lab member. You do not rewrite or improve the draft -- you \
decide whether it may be released as-is, or must be blocked and \
escalated to a human safety officer instead.

You will be given the original user request, which specialist produced \
the draft, the tools that specialist actually called this turn and what \
they returned, and the draft response itself.

{rules}
Respond with ONLY strict JSON, no other text:
{{"verdict": "clear" or "escalate", "reasoning": "<one sentence>"}}
"""


def _gate_prompt_for(specialist_name: str) -> str:
    rules = _SAFETY_GATE_RULES if specialist_name == "safety" else _NON_SAFETY_GATE_RULES
    return _GATE_EVALUATOR_SYSTEM_PROMPT.format(rules=rules)


def enforce_safety_gate(specialist_name: str, user_input: str, tool_call_log: list[dict], draft_text: str) -> dict:
    if _already_escalated(tool_call_log):
        return _clear(draft_text, "specialist already escalated via escalate_to_safety_officer")

    unresolved = _unresolved_lookups(tool_call_log)
    if unresolved:
        names = [call["name"] for call in unresolved]
        return _force_escalate(
            specialist_name, user_input, tool_call_log, draft_text, reasoning=f"unresolved lookup(s): {names}"
        )

    if _vision_hazard_flagged(tool_call_log):
        return _force_escalate(
            specialist_name,
            user_input,
            tool_call_log,
            draft_text,
            reasoning="analyze_image's hazard-scan pass flagged findings that require review, regardless of how the draft frames them",
        )

    deterministic_flag = _contains_hazard_signal(draft_text)
    llm_verdict = llm_groundedness_check(user_input, specialist_name, tool_call_log, draft_text)

    if llm_verdict["verdict"] == "escalate":
        # Attribute to whichever check actually fired, even when both did --
        # a scorecard reader needs to know it was the LLM's judgment, not
        # let a truthy-but-unrelated "clear" reasoning string leak through.
        reasoning = llm_verdict.get("reasoning") or "LLM groundedness check flagged this response"
        return _force_escalate(specialist_name, user_input, tool_call_log, draft_text, reasoning=reasoning)

    if deterministic_flag:
        return _force_escalate(
            specialist_name,
            user_input,
            tool_call_log,
            draft_text,
            reasoning="deterministic hazard-keyword match in the draft response",
        )

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
            system=_gate_prompt_for(specialist_name), messages=[{"role": "user", "content": prompt}], max_tokens=256
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
    # Found live against Ollama/llama3.1: a tool call with a malformed
    # argument (wrong parameter name) errors out inside dispatch_tool,
    # returning {"error": ...} -- no "found" key at all, so this used to
    # slip past the deterministic check entirely and rely on the LLM
    # layer noticing on its own. A tool call that failed to run is exactly
    # as unresolved as one that returned found: false; treat it the same.
    return [
        call
        for call in tool_call_log
        if isinstance(call["result"], dict) and (call["result"].get("found") is False or "error" in call["result"])
    ]


# Deliberately generous phrases for "the hazard-scan pass found nothing" --
# false negatives here (treating a real finding as "nothing") are the
# expensive direction; false positives just mean an occasional benign scan
# routes through the LLM check too, which is cheap.
_EMPTY_HAZARD_SCAN_PHRASES = ("no findings", "none found", "nothing found", "no issues", "found nothing")


def _vision_hazard_flagged(tool_call_log: list[dict]) -> bool:
    for call in tool_call_log:
        if call["name"] != "analyze_image":
            continue
        result = call.get("result")
        if not isinstance(result, dict):
            continue
        findings = (result.get("hazard_scan_findings") or "").strip().lower()
        if findings and not any(phrase in findings for phrase in _EMPTY_HAZARD_SCAN_PHRASES):
            return True
    return False


def _contains_hazard_signal(text: str) -> bool:
    return _HAZARD_PATTERN.search(text) is not None


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
