from labmate import guardrails


def test_already_escalated_passes_through_without_calling_llm(monkeypatch):
    def _boom(*_args, **_kwargs):
        raise AssertionError("llm_groundedness_check should not be called when already escalated")

    monkeypatch.setattr(guardrails, "llm_groundedness_check", _boom)

    tool_call_log = [{"name": "escalate_to_safety_officer", "input": {}, "result": {"escalated": True}}]
    result = guardrails.enforce_safety_gate("safety", "is this safe?", tool_call_log, "I've escalated this.")

    assert result["verdict"] == "clear"
    assert result["response_text"] == "I've escalated this."


def test_unresolved_lookup_forces_escalation_without_calling_llm(monkeypatch):
    def _boom(*_args, **_kwargs):
        raise AssertionError("llm_groundedness_check should not be called when a lookup is unresolved")

    monkeypatch.setattr(guardrails, "llm_groundedness_check", _boom)

    calls = []
    monkeypatch.setattr(
        guardrails,
        "dispatch_tool",
        lambda name, tool_input: calls.append((name, tool_input)) or {"escalated": True, "queued_at": "now"},
    )

    tool_call_log = [{"name": "lookup_sds", "input": {"substance": "unobtainium"}, "result": {"found": False}}]
    result = guardrails.enforce_safety_gate("safety", "is unobtainium dangerous?", tool_call_log, "It should be fine.")

    assert result["verdict"] == "escalate"
    assert calls and calls[0][0] == "escalate_to_safety_officer"


def test_no_hazard_signal_and_llm_clears_passes_through(monkeypatch):
    monkeypatch.setattr(guardrails, "llm_groundedness_check", lambda *a, **kw: {"verdict": "clear", "reasoning": "grounded"})

    result = guardrails.enforce_safety_gate("literature", "what's new on X?", [], "Here's a summary of recent papers.")

    assert result["verdict"] == "clear"
    assert result["response_text"] == "Here's a summary of recent papers."


def test_deterministic_hazard_keyword_escalates_when_llm_agrees(monkeypatch):
    monkeypatch.setattr(
        guardrails, "llm_groundedness_check", lambda *a, **kw: {"verdict": "escalate", "reasoning": "unsupported claim"}
    )
    calls = []
    monkeypatch.setattr(
        guardrails,
        "dispatch_tool",
        lambda name, tool_input: calls.append((name, tool_input)) or {"escalated": True, "queued_at": "now"},
    )

    result = guardrails.enforce_safety_gate(
        "literature", "tell me about this reagent", [], "It's safe to dispose of this down the drain."
    )

    assert result["verdict"] == "escalate"
    assert calls


def test_llm_alone_can_trigger_escalation_with_no_deterministic_flag(monkeypatch):
    """A draft with none of the hardcoded hazard keywords should still
    escalate if the LLM groundedness check flags it -- proving the two
    checks are ORed for escalation, not just the keyword net doing all
    the work.
    """
    monkeypatch.setattr(
        guardrails, "llm_groundedness_check", lambda *a, **kw: {"verdict": "escalate", "reasoning": "unsupported claim"}
    )
    calls = []
    monkeypatch.setattr(
        guardrails,
        "dispatch_tool",
        lambda name, tool_input: calls.append((name, tool_input)) or {"escalated": True, "queued_at": "now"},
    )

    result = guardrails.enforce_safety_gate("literature", "tell me about this reagent", [], "Here is a neutral summary.")

    assert result["verdict"] == "escalate"
    assert calls


def test_llm_groundedness_check_fails_closed_on_error(monkeypatch):
    def _raise(*_args, **_kwargs):
        raise ConnectionError("no backend configured")

    monkeypatch.setattr(guardrails, "create_message", _raise)

    result = guardrails.llm_groundedness_check("q", "safety", [], "draft")

    assert result["verdict"] == "escalate"


def test_parse_verdict_handles_markdown_fenced_json():
    text = '```json\n{"verdict": "clear", "reasoning": "ok"}\n```'
    result = guardrails._parse_verdict(text)
    assert result["verdict"] == "clear"


def test_parse_verdict_fails_closed_on_garbage():
    result = guardrails._parse_verdict("not json at all")
    assert result["verdict"] == "escalate"
