"""Safety specialist -- the centerpiece of this project.

M1: real lookup_sds / lookup_biosafety_level tools, and
escalate_to_safety_officer actually logs to the local review queue
(var/escalations.jsonl -- M4 builds a real UI on top of this store).

M2: adds search_sop_handbook (the hand-authored SOP corpus), and
get_environmental_state / log_environmental_state -- static SDS/BSL data
can't answer "is it safe to run this right now given what's happening on
the adjacent bench," which is exactly the gap environmental state exists
to cover. An expired environmental-state entry reads as unknown, never as
the last-known value (see labmate.memory.store).

The enforced code-level gate (M3) is NOT wired up yet: this specialist's
discipline is still prompt-based at this milestone, which is exactly why
M3 exists -- a prompt-based rule is a weaker guarantee than a code-level
one, and this milestone doesn't claim otherwise.
"""

from labmate.mcp_server.tools import TOOL_SCHEMAS as _ALL_TOOLS

SYSTEM_PROMPT = """\
A lab member is asking about the safety of a substance, spill, or \
procedure. Use lookup_sds, lookup_biosafety_level, and \
search_sop_handbook -- never answer from training knowledge alone. If the \
question mentions a specific bench or location, also call \
get_environmental_state for it; if that comes back found: false because \
the last entry expired, treat the environment as unknown, not as still \
matching whatever was last logged. Use search_past_qa to check whether \
this lab has seen something similar before. If any lookup returns \
found: false, that means UNRESOLVED, not "not hazardous" -- call \
escalate_to_safety_officer rather than guessing or reassuring the user. \
Likewise call escalate_to_safety_officer whenever the situation is \
ambiguous, the retrieved source doesn't clearly cover the specific \
scenario asked about, or there is any physical-harm implication you are \
not certain about. If a lab member reports a current condition at a \
bench (e.g. an active heat source, an in-progress procedure), call \
log_environmental_state so the next question about that bench has it \
available. You are not being graded on how often you can answer directly \
-- you are being graded on never giving a false "this is fine."
"""

TOOL_SCHEMAS = [
    t
    for t in _ALL_TOOLS
    if t["name"]
    in {
        "lookup_sds",
        "lookup_biosafety_level",
        "search_sop_handbook",
        "get_environmental_state",
        "log_environmental_state",
        "search_past_qa",
        "escalate_to_safety_officer",
    }
]
