"""M3: the enforced safety escalation gate. Not wired in yet (M0-M2).

When implemented, this must be a hard code path, not a prompt instruction:
if the safety specialist's response doesn't include a call to
escalate_to_safety_officer AND its confidence/coverage signal is below
threshold, the harness blocks the response from reaching the user and
forces escalation instead. A prompt that says "please escalate when unsure"
is exactly the kind of guardrail that silently degrades under adversarial
or ambiguous input — this has to be enforced by code that runs regardless
of what the model decided to do.

See docs/architecture.md for the full design.
"""


def enforce_safety_gate(specialist_name: str, response) -> None:
    raise NotImplementedError("wire up in M3 -- see docs/architecture.md")
