import pytest

from labmate import review_queue
from labmate.mcp_server.tools import dispatch_tool


@pytest.fixture(autouse=True)
def isolated_var_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(review_queue, "VAR_DIR", tmp_path)
    import labmate.mcp_server.tools as tools_module

    monkeypatch.setattr(tools_module, "VAR_DIR", tmp_path)


def test_list_pending_empty_when_nothing_escalated():
    assert review_queue.list_pending() == []


def test_list_pending_shows_escalated_entries():
    dispatch_tool("escalate_to_safety_officer", {"summary": "first", "urgency": "urgent"})
    dispatch_tool("escalate_to_safety_officer", {"summary": "second", "urgency": "routine"})

    pending = review_queue.list_pending()

    assert len(pending) == 2
    assert pending[0]["summary"] == "first"
    assert pending[1]["summary"] == "second"


def test_resolve_marks_entry_resolved_and_removes_from_pending():
    dispatch_tool("escalate_to_safety_officer", {"summary": "needs review", "urgency": "urgent"})

    result = review_queue.resolve(1, "confirmed_hazard", resolved_by="safety officer", note="verified with SDS binder")

    assert result["resolved"] is True
    assert result["entry"]["decision"] == "confirmed_hazard"
    assert result["entry"]["resolved_by"] == "safety officer"
    assert review_queue.list_pending() == []


def test_resolving_one_entry_renumbers_remaining_pending_indices():
    dispatch_tool("escalate_to_safety_officer", {"summary": "first", "urgency": "urgent"})
    dispatch_tool("escalate_to_safety_officer", {"summary": "second", "urgency": "routine"})

    review_queue.resolve(1, "false_positive", resolved_by="alex")

    remaining = review_queue.list_pending()
    assert len(remaining) == 1
    assert remaining[0]["summary"] == "second"

    # after the first resolve, index 1 now refers to what was previously index 2
    result = review_queue.resolve(1, "confirmed_hazard", resolved_by="alex")
    assert result["entry"]["summary"] == "second"


def test_resolve_invalid_index_is_explicit_not_silent():
    result = review_queue.resolve(1, "confirmed_hazard", resolved_by="alex")
    assert result["resolved"] is False
    assert "No pending escalation" in result["note"]
