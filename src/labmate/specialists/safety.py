"""Safety specialist -- the centerpiece of this project.

M1: real lookup_sds / lookup_biosafety_level tools, and
escalate_to_safety_officer actually logs to the local review queue
(var/escalations.jsonl -- M4 builds a real UI on top of this store). The
enforced code-level gate (M3) is NOT wired up yet: this specialist's
discipline is still prompt-based at this milestone, which is exactly why
M3 exists -- a prompt-based rule is a weaker guarantee than a code-level
one, and this milestone doesn't claim otherwise.
"""

from labmate.mcp_server.tools import TOOL_SCHEMAS as _ALL_TOOLS

SYSTEM_PROMPT = """\
A lab member is asking about the safety of a substance, spill, or \
procedure. Use lookup_sds and lookup_biosafety_level -- never answer from \
training knowledge alone. If a lookup returns found: false, that means \
UNRESOLVED, not "not hazardous" -- call escalate_to_safety_officer rather \
than guessing or reassuring the user. Likewise call \
escalate_to_safety_officer whenever the situation is ambiguous, the \
retrieved source doesn't clearly cover the specific scenario asked about, \
or there is any physical-harm implication you are not certain about. You \
are not being graded on how often you can answer directly -- you are \
being graded on never giving a false "this is fine."
"""

TOOL_SCHEMAS = [
    t for t in _ALL_TOOLS if t["name"] in {"lookup_sds", "lookup_biosafety_level", "escalate_to_safety_officer"}
]
