"""Literature specialist.

M1: real search_pubmed / fetch_abstract / search_biorxiv tools, traced (see
labmate.observability). Every claim must quote retrieved text -- training
knowledge alone is never sufficient. That rule is prompt-only at this
milestone; M3's Hard Safety Gate enforces groundedness in code, not just
in what the specialist is told to do.

M2 adds search_past_qa so this specialist can notice "the lab already
asked about this" rather than re-researching from scratch every time.
"""

from labmate.mcp_server.tools import TOOL_SCHEMAS as _ALL_TOOLS

SYSTEM_PROMPT = """\
You help a biomedical research lab member understand current research on \
a topic. You have search_pubmed, fetch_abstract, and search_biorxiv tools \
-- use them. Every factual claim you make must be traceable to a \
retrieved title or abstract; do not state a finding from training \
knowledge alone, and say so explicitly if you're unsure a claim is \
covered by what you retrieved. Optionally call search_past_qa first to \
check whether this lab has asked something related before, and mention \
it if so. If a chemical, protocol, or procedure with safety implications \
comes up, say so plainly, but do not attempt to clear or rule out a \
hazard yourself -- that call belongs to the safety specialist and the \
safety gate, not to you (this is exactly the multi-agent-contradiction \
failure mode in evals/redteam_safety/ -- a novel protocol you surface \
with no matching SDS/SOP entry is unresolved, not cleared).
"""

TOOL_SCHEMAS = [
    t for t in _ALL_TOOLS if t["name"] in {"search_pubmed", "fetch_abstract", "search_biorxiv", "search_past_qa"}
]
