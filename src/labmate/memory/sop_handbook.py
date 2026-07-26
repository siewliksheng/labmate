"""M2: a small, hand-authored SOP handbook, searched just-in-time -- never
pre-loaded whole into context. See data/sop_handbook/*.md and README
"Data" for why this is authored rather than sourced from a real
institution (it lets the ambiguous edge cases the eval set needs be
designed deliberately).
"""

from pathlib import Path

_HANDBOOK_DIR = Path(__file__).parent / "data" / "sop_handbook"


def search_sop_handbook(query: str, max_results: int = 3):
    # Known limitation: a query containing a common word (e.g. "about")
    # can produce a low relevance_score match against an unrelated
    # paragraph that happens to contain that word. Not worth a stopword
    # list or a score threshold until this actually causes a bad
    # escalation decision -- the safety specialist's prompt already
    # treats a genuinely empty result as unresolved, and a caller can
    # look at relevance_score itself if this becomes a real problem.
    terms = [t for t in query.lower().split() if t]
    scored = []
    for path in sorted(_HANDBOOK_DIR.glob("*.md")):
        for paragraph in (p.strip() for p in path.read_text(encoding="utf-8").split("\n\n")):
            if not paragraph:
                continue
            lowered = paragraph.lower()
            score = sum(lowered.count(term) for term in terms)
            if score > 0:
                scored.append((score, path.name, paragraph))

    scored.sort(key=lambda item: item[0], reverse=True)
    top = scored[:max_results]
    if not top:
        return {"results": [], "note": "No SOP handbook entry matched this query -- treat as unresolved."}
    return {
        "results": [
            {"source": name, "excerpt": paragraph, "relevance_score": score} for score, name, paragraph in top
        ]
    }
