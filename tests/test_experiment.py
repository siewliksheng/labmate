import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from labmate import experiment
from labmate.memory import store


@pytest.fixture(autouse=True)
def isolated_var_dir(tmp_path, monkeypatch):
    """Every test gets its own var/ so runs (SQLite rows, escalations.jsonl,
    generated reports, the active-experiment pointer) can't leak between
    tests or prior local dev runs.
    """
    monkeypatch.setattr(store, "VAR_DIR", tmp_path)
    monkeypatch.setattr(experiment, "VAR_DIR", tmp_path)
    import labmate.mcp_server.tools as tools_module

    monkeypatch.setattr(tools_module, "VAR_DIR", tmp_path)


def _fake_llm(text: str):
    def _call(system, messages, tools=None, max_tokens=2048):
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], stop_reason="end_turn")

    return _call


def test_start_experiment_runs_prelab_and_returns_checklist(monkeypatch):
    checklist = {
        "required_ppe": ["gloves"],
        "items": [{"item": "ethanol", "resolved": True, "hazard_summary": "flammable"}],
        "unresolved_count": 0,
    }
    monkeypatch.setattr(experiment, "create_message", _fake_llm(json.dumps(checklist)))

    result = experiment.start_experiment("Ethanol precipitation of DNA")

    assert result["checklist"]["unresolved_count"] == 0
    exp = store.get_experiment(result["experiment_id"])
    assert exp["status"] == "prelab_ready"
    assert store.get_active_experiment_id() == result["experiment_id"]


def test_signoff_blocks_when_unresolved_items_not_acknowledged(monkeypatch):
    checklist = {
        "required_ppe": [],
        "items": [{"item": "mystery reagent", "resolved": False, "hazard_summary": "no matching entry found"}],
        "unresolved_count": 1,
    }
    monkeypatch.setattr(experiment, "create_message", _fake_llm(json.dumps(checklist)))

    result = experiment.start_experiment("Handling mystery reagent")
    experiment_id = result["experiment_id"]

    blocked = experiment.sign_off(experiment_id, "alex")
    assert blocked["signed_off"] is False

    acknowledged = experiment.sign_off(experiment_id, "alex", acknowledge_unresolved=True)
    assert acknowledged["signed_off"] is True

    exp = store.get_experiment(experiment_id)
    assert exp["status"] == "lab"


def test_prelab_checklist_parse_failure_fails_closed_to_unresolved(monkeypatch):
    monkeypatch.setattr(experiment, "create_message", _fake_llm("not valid json at all"))

    result = experiment.start_experiment("Some experiment")

    assert result["checklist"]["unresolved_count"] >= 1


def test_prelab_checklist_reformat_retry_succeeds_after_initial_prose(monkeypatch):
    """Matches what was actually observed live against Ollama/llama3.1:
    the model's final turn is prose, not JSON -- the retry (a second,
    tool-free call asking it to reformat) gets a clean parse.
    """
    valid_checklist = {"required_ppe": ["gloves"], "items": [], "unresolved_count": 0}
    responses = iter(
        [
            "The required PPE includes gloves. No unresolved items.",  # first turn: prose, not JSON
            json.dumps(valid_checklist),  # reformat retry: clean JSON
        ]
    )

    def _sequenced_llm(system, messages, tools=None, max_tokens=2048):
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=next(responses))], stop_reason="end_turn")

    monkeypatch.setattr(experiment, "create_message", _sequenced_llm)

    result = experiment.start_experiment("Some experiment")

    assert result["checklist"]["unresolved_count"] == 0
    assert result["checklist"]["required_ppe"] == ["gloves"]


def test_prelab_checklist_fails_closed_when_retry_also_fails(monkeypatch):
    monkeypatch.setattr(experiment, "create_message", _fake_llm("still not json, even on retry"))

    result = experiment.start_experiment("Some experiment")

    assert result["checklist"]["unresolved_count"] >= 1
    assert "reformat retry" in result["checklist"]["note"]


def test_record_observation_and_report_includes_it(monkeypatch):
    checklist = {"required_ppe": [], "items": [], "unresolved_count": 0}
    monkeypatch.setattr(experiment, "create_message", _fake_llm(json.dumps(checklist)))

    result = experiment.start_experiment("Simple experiment")
    experiment_id = result["experiment_id"]
    experiment.sign_off(experiment_id, "alex")

    experiment.record_observation(experiment_id, "text", "OD600 = 0.42 at t=30min", note="flask A")

    def fake_report_call(system, messages, tools=None, max_tokens=2048):
        prompt_text = messages[0]["content"]
        assert "OD600 = 0.42" in prompt_text  # the observation actually reached the synthesis prompt
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text="# Report\n\nOD600 = 0.42 at t=30min")],
            stop_reason="end_turn",
        )

    monkeypatch.setattr(experiment, "create_message", fake_report_call)
    paths = experiment.generate_report(experiment_id)

    assert "OD600" in Path(paths["markdown"]).read_text(encoding="utf-8")
    html_text = Path(paths["html"]).read_text(encoding="utf-8")
    assert "OD600" in html_text
    assert "<html" in html_text  # actually rendered, not just the raw markdown copied over

    exp = store.get_experiment(experiment_id)
    assert exp["status"] == "reported"
    assert store.get_active_experiment_id() is None


def test_escalation_during_experiment_is_tagged_and_surfaced(monkeypatch):
    checklist = {"required_ppe": [], "items": [], "unresolved_count": 0}
    monkeypatch.setattr(experiment, "create_message", _fake_llm(json.dumps(checklist)))

    result = experiment.start_experiment("Some experiment")
    experiment_id = result["experiment_id"]
    experiment.sign_off(experiment_id, "alex")

    from labmate.mcp_server.tools import dispatch_tool

    dispatch_tool("escalate_to_safety_officer", {"summary": "test escalation", "urgency": "urgent"})

    escalations = experiment._get_escalations_for_experiment(experiment_id)
    assert len(escalations) == 1
    assert escalations[0]["summary"] == "test escalation"


def test_agent_run_tags_qa_with_active_experiment(monkeypatch):
    checklist = {"required_ppe": [], "items": [], "unresolved_count": 0}
    monkeypatch.setattr(experiment, "create_message", _fake_llm(json.dumps(checklist)))

    result = experiment.start_experiment("Some experiment")
    experiment_id = result["experiment_id"]
    experiment.sign_off(experiment_id, "alex")

    import labmate.agent as agent_module

    monkeypatch.setattr(agent_module, "create_message", _fake_llm("Here's what I found."))
    monkeypatch.setattr(
        agent_module,
        "enforce_safety_gate",
        lambda specialist_name, user_input, tool_call_log, draft_text: {
            "verdict": "clear",
            "response_text": draft_text,
            "reasoning": "test",
        },
    )

    agent_module.run("what's new on X?")

    qa = store.get_qa_history_for_experiment(experiment_id)
    assert len(qa) == 1
    assert qa[0]["user_input"] == "what's new on X?"
