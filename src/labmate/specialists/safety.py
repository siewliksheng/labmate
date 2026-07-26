"""Safety specialist -- the centerpiece of this project.

Design invariant, enforced (not just prompted) starting M3: no tool ever
gives this specialist a way to declare something "safe" -- only to look up
a source, or, when uncertain, escalate to a human. M0 has neither the
lookup tools nor the enforced gate yet, so it must decline to answer at all
rather than guess. A wrong answer here risks physical harm, so "decline
until the real capability exists" is the only acceptable M0 behavior.

See docs/architecture.md for the full escalation-gate design.
"""

SYSTEM_PROMPT = """\
A lab member is asking about the safety of a substance, spill, or \
procedure. You do NOT have safety-data-sheet lookup tools yet (arriving \
M1) and the enforced escalation gate is not wired up yet (M3). Because a \
wrong answer here can cause physical harm, you must NOT attempt to answer \
safety questions in this milestone -- always say this capability is not \
live yet and direct the user to their lab's safety officer or SDS binder.
"""

TOOL_SCHEMAS: list = []  # lookup_sds, lookup_biosafety_level (M1), escalate_to_safety_officer (M1, enforced M3)
