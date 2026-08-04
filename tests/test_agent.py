"""Tests for the agent loop's recovery from a tool call the model wrote
as plain text instead of emitting as a real tool_use block -- observed
live with Ollama/llama3.1.
"""

from labmate.agent import _tool_call_emitted_as_text

TOOLS = [
    {"name": "search_biorxiv", "description": "...", "input_schema": {}},
    {"name": "search_pubmed", "description": "...", "input_schema": {}},
]


def test_recovers_the_exact_shape_observed_live():
    text = '{"name": "search_biorxiv", "parameters": {"query": "PNIPAM hydrogel"}}'
    assert _tool_call_emitted_as_text(text, TOOLS) == ("search_biorxiv", {"query": "PNIPAM hydrogel"})


def test_recovers_when_wrapped_in_surrounding_prose():
    text = 'The search found nothing. Let me try BioRxiv.\n\n{"name": "search_pubmed", "arguments": {"query": "x"}}'
    assert _tool_call_emitted_as_text(text, TOOLS) == ("search_pubmed", {"query": "x"})


def test_ignores_an_ordinary_answer():
    assert _tool_call_emitted_as_text("The optimal temperature is around 32C.", TOOLS) is None


def test_ignores_json_that_is_not_a_tool_call():
    assert _tool_call_emitted_as_text('{"verdict": "clear", "reasoning": "ok"}', TOOLS) is None


def test_ignores_a_hallucinated_tool_name():
    """A tool this specialist doesn't have must not be dispatched just
    because the model named it.
    """
    text = '{"name": "delete_all_records", "parameters": {}}'
    assert _tool_call_emitted_as_text(text, TOOLS) is None


def test_ignores_a_tool_call_with_no_arguments_object():
    assert _tool_call_emitted_as_text('{"name": "search_pubmed"}', TOOLS) is None


def test_returns_none_when_specialist_has_no_tools():
    text = '{"name": "search_biorxiv", "parameters": {"query": "x"}}'
    assert _tool_call_emitted_as_text(text, []) is None
