"""M0: hardcoded keyword routing.

Deliberately the dumbest thing that could work — a real classifier/router is
M5. Keeping this crude on purpose makes the M5 upgrade a legible, honest
diff (with a before/after eval comparison) instead of a rewrite that hides
whatever improvement it actually bought.
"""

SAFETY_KEYWORDS = ("safe", "danger", "hazard", "spill", "toxic", "dispose", "expose", "harm")
LITERATURE_KEYWORDS = ("latest", "research", "paper", "study", "literature", "published")


def route(user_input: str, has_image: bool = False) -> str:
    lowered = user_input.lower()

    # Safety wins every tie, including against an attached image — see
    # docs/architecture.md, "why safety routing wins ties".
    if any(kw in lowered for kw in SAFETY_KEYWORDS):
        return "safety"
    if has_image:
        return "vision"
    if any(kw in lowered for kw in LITERATURE_KEYWORDS):
        return "literature"
    return "literature"  # default: most lab questions are "what do we know about X"
