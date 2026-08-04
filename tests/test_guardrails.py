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


def test_tool_call_error_forces_escalation_without_calling_llm(monkeypatch):
    """Found live against Ollama/llama3.1: a malformed tool argument
    errors out inside dispatch_tool ({"error": ...}, no "found" key at
    all) -- that used to slip past this deterministic check entirely.
    """

    def _boom(*_args, **_kwargs):
        raise AssertionError("llm_groundedness_check should not be called when a tool call errored")

    monkeypatch.setattr(guardrails, "llm_groundedness_check", _boom)
    monkeypatch.setattr(guardrails, "dispatch_tool", lambda name, tool_input: {"escalated": True, "queued_at": "now"})

    tool_call_log = [
        {
            "name": "lookup_biosafety_level",
            "input": {"substance": "formaldehyde"},
            "result": {"error": "_lookup_biosafety_level() got an unexpected keyword argument 'substance'"},
        }
    ]
    result = guardrails.enforce_safety_gate("safety", "is formaldehyde dangerous?", tool_call_log, "Should be fine.")

    assert result["verdict"] == "escalate"


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


def test_deterministic_reasoning_not_masked_by_a_clear_llm_verdict(monkeypatch):
    """Found by evals/redteam_safety while stubbing the LLM check to
    "clear" (the worst-case eval methodology): the deterministic keyword
    net fired, but the reported reasoning was the LLM's own "clear"
    justification leaking through, not attributed to the check that
    actually caused the escalation.
    """
    monkeypatch.setattr(
        guardrails, "llm_groundedness_check", lambda *a, **kw: {"verdict": "clear", "reasoning": "looked fine to me"}
    )
    monkeypatch.setattr(guardrails, "dispatch_tool", lambda name, tool_input: {"escalated": True, "queued_at": "now"})

    result = guardrails.enforce_safety_gate(
        "literature", "tell me about this reagent", [], "It's safe to dispose of this down the drain."
    )

    assert result["verdict"] == "escalate"
    assert "looked fine to me" not in result["reasoning"]
    assert "hazard-keyword" in result["reasoning"]


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


def test_vision_hazard_scan_findings_force_escalation_without_calling_llm(monkeypatch):
    """docs/architecture.md gap #5 promised this from M1; it wasn't
    actually wired into the gate until M5's eval suite exercised it.
    """

    def _boom(*_args, **_kwargs):
        raise AssertionError("llm_groundedness_check should not be called when the hazard-scan pass flagged something")

    monkeypatch.setattr(guardrails, "llm_groundedness_check", _boom)
    calls = []
    monkeypatch.setattr(
        guardrails,
        "dispatch_tool",
        lambda name, tool_input: calls.append((name, tool_input)) or {"escalated": True, "queued_at": "now"},
    )

    tool_call_log = [
        {
            "name": "analyze_image",
            "input": {"image_path": "flask.jpg"},
            "result": {
                "found": True,
                "description": "Cell culture flask, media appears normal in the central region.",
                "hazard_scan_findings": "A hairline crack is visible along the flask's glass edge.",
            },
        }
    ]
    result = guardrails.enforce_safety_gate("vision", "does this culture look okay?", tool_call_log, "Looks fine to keep incubating.")

    assert result["verdict"] == "escalate"
    assert calls


def test_vision_hazard_scan_no_findings_does_not_force_escalation(monkeypatch):
    monkeypatch.setattr(guardrails, "llm_groundedness_check", lambda *a, **kw: {"verdict": "clear", "reasoning": "grounded"})

    tool_call_log = [
        {
            "name": "analyze_image",
            "input": {"image_path": "flask.jpg"},
            "result": {
                "found": True,
                "description": "Cell culture flask, confluent monolayer.",
                "hazard_scan_findings": "No findings -- no cracks, discoloration, or contamination observed.",
            },
        }
    ]
    result = guardrails.enforce_safety_gate("vision", "does this culture look okay?", tool_call_log, "This looks like a healthy, confluent monolayer.")

    assert result["verdict"] == "clear"


def test_hazard_pattern_does_not_false_positive_on_substrings():
    """Naive substring matching fired on "p(harm)aceutical" and "(safe)ty",
    which would escalate essentially every pharma or lab-safety-adjacent
    literature answer. Word-boundary matching fixes it.
    """
    assert not guardrails._contains_hazard_signal("Recent pharmaceutical research on this compound.")
    assert not guardrails._contains_hazard_signal("The paper discusses laboratory safety culture.")
    assert not guardrails._contains_hazard_signal("Long exposures were used to image the sample.")


def test_hazard_pattern_still_catches_real_hazard_language():
    for text in [
        "It's safe to dispose of this down the drain.",
        "This reagent is harmless at that concentration.",
        "There is no exposure hazard here.",
        "That should be okay to do.",
        "The compound is nontoxic.",
        # Compound word -- the eval suite caught this being silently
        # dropped when substring matching became word-boundary matching.
        "Put the towels in the biohazard bin, should be fine.",
    ]:
        assert guardrails._contains_hazard_signal(text), text


def test_gate_prompt_is_specialist_aware():
    safety_prompt = guardrails._gate_prompt_for("safety")
    literature_prompt = guardrails._gate_prompt_for("literature")

    assert "every factual claim in the draft traces to a retrieved tool" in safety_prompt
    assert "Reporting a lack of information is not a safety claim" in literature_prompt
    assert safety_prompt != literature_prompt


def test_literature_draft_reporting_no_findings_is_not_escalated(monkeypatch):
    """The exact failure the user hit: a literature answer saying "I
    couldn't find specifics, here are related papers" was escalated for
    "claiming an optimal temperature without a matching SDS entry."
    """
    monkeypatch.setattr(
        guardrails, "llm_groundedness_check", lambda *a, **kw: {"verdict": "clear", "reasoning": "no safety claim made"}
    )

    draft = (
        "Based on the search results, I was unable to find specific information regarding "
        "optimal temperature and crosslinking time for PNIPAM hydrogels in microfluidic channels. "
        "However, the paper 'Lower Critical Solution Temperature Phase Transition' may be relevant."
    )
    result = guardrails.enforce_safety_gate(
        "literature",
        "What is the optimal crosslinking time for PNIPAM hydrogel?",
        [{"name": "search_pubmed", "input": {"query": "PNIPAM"}, "result": {"results": [{"pmid": "1"}]}}],
        draft,
    )

    assert result["verdict"] == "clear"
    assert result["response_text"] == draft


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
