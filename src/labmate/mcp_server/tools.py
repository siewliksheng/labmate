"""Tool schemas for M1 onward, exposed both to the plain agent loop and as an
MCP server (server.py). Not called yet in M0 -- the orchestrator/specialists
currently run with TOOL_SCHEMAS = [] (see specialists/*.py).

Design notes to keep in mind as these get implemented:
- escalate_to_safety_officer exists from the start of M1, before the gate
  that enforces its use lands in M3 -- the tool being available is not the
  same as its use being guaranteed, which is exactly why the M3 code-level
  gate is necessary rather than optional.
- lookup_sds / lookup_biosafety_level return grounding passages, never a
  bare verdict -- the specialist must quote what it found, not summarize it
  into a confident-sounding conclusion.
- analyze_image returns a description + confidence signal, never a binary
  safe/unsafe classification -- that framing decision belongs to the
  safety gate, not to the vision specialist.
"""

from typing import Any

TOOL_SCHEMAS = [
    {
        "name": "search_pubmed",
        "description": "Search PubMed for recent papers on a topic. Returns titles, IDs, and short summaries -- call fetch_abstract for full text of a specific result.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer", "default": 10},
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_biorxiv",
        "description": "Search bioRxiv/medRxiv preprints for a topic. Same return shape as search_pubmed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer", "default": 10},
            },
            "required": ["query"],
        },
    },
    {
        "name": "analyze_image",
        "description": (
            "Analyze a lab sample image (microscopy, culture plate, blot). "
            "Returns a structured description and a confidence score -- "
            "never a safe/unsafe verdict, which is not this tool's job."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"image_path": {"type": "string"}},
            "required": ["image_path"],
        },
    },
    {
        "name": "lookup_sds",
        "description": "Retrieve the safety data sheet (GHS hazard classes, handling, disposal) for a named substance. Returns the source passage, not a summary.",
        "input_schema": {
            "type": "object",
            "properties": {"substance": {"type": "string"}},
            "required": ["substance"],
        },
    },
    {
        "name": "lookup_biosafety_level",
        "description": "Look up the required biosafety level and handling protocol for a named organism or sample type.",
        "input_schema": {
            "type": "object",
            "properties": {"organism_or_sample": {"type": "string"}},
            "required": ["organism_or_sample"],
        },
    },
    {
        "name": "escalate_to_safety_officer",
        "description": (
            "Hand off a safety question to a human safety officer instead "
            "of answering it directly. Use whenever no retrieved SDS/"
            "protocol unambiguously covers the situation, or the query "
            "implies physical risk you are not certain about."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "urgency": {"enum": ["routine", "urgent"]},
            },
            "required": ["summary", "urgency"],
        },
    },
]


def dispatch_tool(name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
    handler = _HANDLERS.get(name)
    if handler is None:
        return {"error": f"Unknown tool '{name}'. Available: {list(_HANDLERS)}"}
    return handler(**tool_input)


def _search_pubmed(query: str, max_results: int = 10):
    raise NotImplementedError  # M1: call NCBI E-utilities esearch/esummary


def _search_biorxiv(query: str, max_results: int = 10):
    raise NotImplementedError  # M1: call the bioRxiv/medRxiv API


def _analyze_image(image_path: str):
    raise NotImplementedError  # M1: Claude vision call + structured output


def _lookup_sds(substance: str):
    raise NotImplementedError  # M1: PubChem GHS lookup


def _lookup_biosafety_level(organism_or_sample: str):
    raise NotImplementedError  # M1: local biosafety-level reference table


def _escalate_to_safety_officer(summary: str, urgency: str):
    raise NotImplementedError  # M1: log to the review queue (M4 builds the UI on top)


_HANDLERS = {
    "search_pubmed": _search_pubmed,
    "search_biorxiv": _search_biorxiv,
    "analyze_image": _analyze_image,
    "lookup_sds": _lookup_sds,
    "lookup_biosafety_level": _lookup_biosafety_level,
    "escalate_to_safety_officer": _escalate_to_safety_officer,
}
