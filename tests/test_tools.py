import json

import pytest

from labmate.mcp_server.tools import dispatch_tool
from labmate.paths import VAR_DIR


def test_biosafety_lookup_known_organism():
    result = dispatch_tool("lookup_biosafety_level", {"organism_or_sample": "E. coli K-12"})
    assert result["found"] is True
    assert result["level"] == "BSL-1"


def test_biosafety_lookup_unknown_organism_is_unresolved_not_safe():
    result = dispatch_tool("lookup_biosafety_level", {"organism_or_sample": "a completely novel synthetic organism xyz123"})
    assert result["found"] is False


def test_escalation_logs_to_local_queue(tmp_path, monkeypatch):
    monkeypatch.setattr("labmate.mcp_server.tools.VAR_DIR", tmp_path)
    result = dispatch_tool(
        "escalate_to_safety_officer", {"summary": "test escalation", "urgency": "urgent"}
    )
    assert result["escalated"] is True

    log_path = tmp_path / "escalations.jsonl"
    assert log_path.exists()
    entry = json.loads(log_path.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert entry["summary"] == "test escalation"
    assert entry["urgency"] == "urgent"
    assert entry["status"] == "pending"


def test_dispatch_tool_traces_every_call():
    """M1's headline claim: every tool call gets a span, with no external
    tracing backend required.

    Checks the real local fallback file (var/spans.jsonl) rather than a
    monkeypatched path -- OpenTelemetry's global TracerProvider is a true
    process-wide singleton that silently refuses replacement after first
    use, so redirecting it mid-test-session isn't meaningful. This is the
    actual artifact the running process produces, with no Langfuse
    credentials or network access required.
    """
    dispatch_tool("lookup_biosafety_level", {"organism_or_sample": "e. coli k-12"})

    spans_path = VAR_DIR / "spans.jsonl"
    assert spans_path.exists()
    spans = [json.loads(line) for line in spans_path.read_text(encoding="utf-8").strip().splitlines()]
    matching = [s for s in spans if s["name"] == "tool:lookup_biosafety_level"]
    assert matching
    assert "duration_ms" in matching[-1]["attributes"]


def test_unknown_tool_returns_recoverable_error():
    result = dispatch_tool("nonexistent_tool", {})
    assert "error" in result
    assert "Available" in result["error"]


@pytest.mark.network
def test_search_pubmed_returns_real_results():
    result = dispatch_tool("search_pubmed", {"query": "CRISPR lipid nanoparticle delivery", "max_results": 3})
    assert "results" in result
    assert len(result["results"]) > 0
    assert result["results"][0]["pmid"]


@pytest.mark.network
def test_search_biorxiv_returns_real_results():
    result = dispatch_tool("search_biorxiv", {"query": "single cell RNA sequencing", "max_results": 3})
    assert "results" in result
    assert len(result["results"]) > 0


@pytest.mark.network
def test_lookup_sds_known_substance():
    result = dispatch_tool("lookup_sds", {"substance": "formaldehyde"})
    assert result["found"] is True
    assert result["cid"]


@pytest.mark.network
def test_lookup_sds_unknown_substance_is_unresolved_not_safe():
    result = dispatch_tool("lookup_sds", {"substance": "definitely-not-a-real-chemical-xyz123"})
    assert result["found"] is False
