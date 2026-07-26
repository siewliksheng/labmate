from labmate.mcp_server.tools import TOOL_SCHEMAS
from labmate.orchestrator import route


def test_safety_keyword_routes_to_safety():
    assert route("is this reagent toxic if I spill it?") == "safety"


def test_image_with_no_safety_keyword_routes_to_vision():
    assert route("what is this?", has_image=True) == "vision"


def test_safety_wins_tie_against_image():
    assert route("is this contamination dangerous?", has_image=True) == "safety"


def test_literature_keyword_routes_to_literature():
    assert route("what's the latest research on CRISPR delivery?") == "literature"


def test_default_routes_to_literature():
    assert route("tell me about lipid nanoparticles") == "literature"


def test_escalation_tool_exists_in_planned_schema():
    names = {schema["name"] for schema in TOOL_SCHEMAS}
    assert "escalate_to_safety_officer" in names
