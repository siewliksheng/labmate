"""Unit-level eval: does dispatch_tool route correctly and fail legibly?"""

import pytest

from radreport_agent.mcp_server.tools import dispatch_tool


def test_unknown_tool_returns_recoverable_error():
    result = dispatch_tool("nonexistent_tool", {})
    assert "error" in result
    assert "Available" in result["error"]


def test_known_tool_dispatches():
    with pytest.raises(NotImplementedError):
        dispatch_tool("lookup_radlex_term", {"phrase": "ground glass opacity"})
