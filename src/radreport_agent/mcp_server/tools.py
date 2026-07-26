"""Tool schemas and implementations, exposed both as plain functions (for the
bare agent loop in agent.py) and as an MCP server (server.py).

Design notes worth keeping as you iterate v1 -> v2 (this diff is a portfolio
artifact, see README "Results" table):
- Error messages must teach recovery, not just state failure.
- Return payloads should be small; a tool that dumps a whole prior report
  instead of a summary + pointer is a design bug, not a convenience.
- Clinical scores (Lung-RADS, Fleischner) are computed here in code, never
  left to the model to assert.
"""

from typing import Any

TOOL_SCHEMAS = [
    {
        "name": "search_prior_reports",
        "description": (
            "Search this patient's prior radiology reports by modality and/or "
            "date range. Returns short summaries with report IDs, not full "
            "text -- call get_report_by_id if you need the full text of a "
            "specific prior."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "patient_id": {"type": "string"},
                "modality": {"type": "string", "description": "e.g. CT, CXR, MRI"},
                "since": {"type": "string", "description": "ISO date, optional"},
            },
            "required": ["patient_id"],
        },
    },
    {
        "name": "lookup_radlex_term",
        "description": "Normalize a free-text finding phrase to its RadLex ID and preferred term.",
        "input_schema": {
            "type": "object",
            "properties": {"phrase": {"type": "string"}},
            "required": ["phrase"],
        },
    },
    {
        "name": "compute_lungrads_category",
        "description": (
            "Compute the Lung-RADS category from nodule characteristics. "
            "Use this instead of reasoning about the category yourself."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "nodule_type": {"enum": ["solid", "part-solid", "ground-glass"]},
                "size_mm": {"type": "number"},
                "prior_size_mm": {"type": "number"},
            },
            "required": ["nodule_type", "size_mm"],
        },
    },
    {
        "name": "get_followup_guideline",
        "description": "Look up the Fleischner Society follow-up recommendation for a pulmonary nodule.",
        "input_schema": {
            "type": "object",
            "properties": {
                "size_mm": {"type": "number"},
                "risk_category": {"enum": ["low", "high"]},
                "nodule_count": {"enum": ["single", "multiple"]},
            },
            "required": ["size_mm", "risk_category", "nodule_count"],
        },
    },
]


def dispatch_tool(name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
    handler = _HANDLERS.get(name)
    if handler is None:
        return {"error": f"Unknown tool '{name}'. Available: {list(_HANDLERS)}"}
    return handler(**tool_input)


def _search_prior_reports(patient_id: str, modality: str | None = None, since: str | None = None):
    # TODO: query Postgres seeded from Synthea/MIMIC-CXR metadata
    raise NotImplementedError


def _lookup_radlex_term(phrase: str):
    # TODO: call UMLS/RadLex API or a local cached mapping
    raise NotImplementedError


def _compute_lungrads_category(
    nodule_type: str, size_mm: float, prior_size_mm: float | None = None
):
    # TODO: implement actual Lung-RADS v2022 logic
    raise NotImplementedError


def _get_followup_guideline(size_mm: float, risk_category: str, nodule_count: str):
    # TODO: implement Fleischner 2017 table lookup
    raise NotImplementedError


_HANDLERS = {
    "search_prior_reports": _search_prior_reports,
    "lookup_radlex_term": _lookup_radlex_term,
    "compute_lungrads_category": _compute_lungrads_category,
    "get_followup_guideline": _get_followup_guideline,
}
