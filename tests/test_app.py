"""Tests the flow logic in labmate.app by monkeypatching its own thin
ask_select/ask_text/ask_confirm wrappers (not questionary's Question/.ask()
protocol directly) -- each wrapper is patched to a small scripted sequence
of canned answers matching the order the flow actually calls it in.
"""

import json
from types import SimpleNamespace

import pytest

from labmate import app, experiment, review_queue
from labmate.memory import store


@pytest.fixture(autouse=True)
def isolated_var_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "VAR_DIR", tmp_path)
    monkeypatch.setattr(experiment, "VAR_DIR", tmp_path)
    monkeypatch.setattr(app, "VAR_DIR", tmp_path)
    monkeypatch.setattr(review_queue, "VAR_DIR", tmp_path)
    import labmate.mcp_server.tools as tools_module

    monkeypatch.setattr(tools_module, "VAR_DIR", tmp_path)


def _sequence(name, *answers):
    it = iter(answers)

    def _fn(*args, **kwargs):
        try:
            return next(it)
        except StopIteration:
            raise AssertionError(f"{name} called more times than scripted: args={args}")

    return _fn


def _fake_llm(text: str):
    def _call(system, messages, tools=None, max_tokens=2048):
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], stop_reason="end_turn")

    return _call


def test_experiment_flow_stops_on_whitespace_only_description_without_calling_llm(monkeypatch):
    def _boom(*_args, **_kwargs):
        raise AssertionError("create_message should never be called for a blank description")

    monkeypatch.setattr(experiment, "create_message", _boom)
    monkeypatch.setattr(app, "ask_text", _sequence("ask_text", "   "))

    app.run_experiment_flow()

    assert store.list_experiments() == []


def test_experiment_flow_completes_and_generates_report_when_no_unresolved_items(monkeypatch):
    checklist = {"required_ppe": [], "items": [], "unresolved_count": 0}
    monkeypatch.setattr(experiment, "create_message", _fake_llm(json.dumps(checklist)))

    monkeypatch.setattr(app, "ask_text", _sequence("ask_text", "Simple experiment", "alex", "what's new on X?"))
    monkeypatch.setattr(app, "ask_select", _sequence("ask_select", "Ask a question", "Finish and generate report"))
    monkeypatch.setattr(app, "ask_confirm", _sequence("ask_confirm", False))  # skip opening the browser

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

    browser_calls = []
    monkeypatch.setattr(app.webbrowser, "open", lambda url: browser_calls.append(url))

    # generate_report's synthesis call happens after the lab loop -- swap
    # create_message again so the same fake serves both without collision.
    monkeypatch.setattr(experiment, "create_message", _fake_llm("# Report\n\nDone."))

    app.run_experiment_flow()

    experiments = store.list_experiments()
    assert len(experiments) == 1
    assert experiments[0]["status"] == "reported"
    assert not browser_calls  # ask_confirm was scripted to say no


def test_experiment_flow_blocks_when_unresolved_and_not_acknowledged(monkeypatch):
    checklist = {
        "required_ppe": [],
        "items": [{"item": "mystery reagent", "resolved": False, "hazard_summary": "no matching entry found"}],
        "unresolved_count": 1,
    }
    monkeypatch.setattr(experiment, "create_message", _fake_llm(json.dumps(checklist)))

    monkeypatch.setattr(app, "ask_text", _sequence("ask_text", "Handling a mystery reagent", "alex"))
    monkeypatch.setattr(app, "ask_confirm", _sequence("ask_confirm", False))  # do NOT acknowledge

    def _boom(*a, **kw):
        raise AssertionError("ask_select should never be reached -- the flow must return before Lab phase")

    monkeypatch.setattr(app, "ask_select", _boom)

    app.run_experiment_flow()

    experiments = store.list_experiments()
    assert len(experiments) == 1
    assert experiments[0]["status"] == "prelab_ready"  # never signed off


def test_resolve_escalation_flow_resolves_the_selected_entry(monkeypatch):
    from labmate.mcp_server.tools import dispatch_tool

    dispatch_tool("escalate_to_safety_officer", {"summary": "first pending item", "urgency": "urgent"})
    dispatch_tool("escalate_to_safety_officer", {"summary": "second pending item", "urgency": "routine"})

    pending = review_queue.list_pending()
    label_for_second = f"[2] {pending[1]['timestamp']}  ({pending[1]['urgency']})  {pending[1]['summary'][:80]}"

    monkeypatch.setattr(app, "ask_select", _sequence("ask_select", label_for_second, "false_positive"))
    monkeypatch.setattr(app, "ask_text", _sequence("ask_text", "alex", "over-cautious, benign question"))

    app.resolve_escalation_flow()

    remaining = review_queue.list_pending()
    assert len(remaining) == 1
    assert remaining[0]["summary"] == "first pending item"


def test_view_report_flow_offers_to_open_existing_report(monkeypatch):
    checklist = {"required_ppe": [], "items": [], "unresolved_count": 0}
    monkeypatch.setattr(experiment, "create_message", _fake_llm(json.dumps(checklist)))
    result = experiment.start_experiment("Some experiment")
    experiment_id = result["experiment_id"]
    experiment.sign_off(experiment_id, "alex")
    monkeypatch.setattr(experiment, "create_message", _fake_llm("# Report\n\nDone."))
    experiment.generate_report(experiment_id)

    experiments = store.list_experiments()
    label = f"{experiments[0]['id']}  [{experiments[0]['status']}]  {experiments[0]['description'][:70]}"

    monkeypatch.setattr(app, "ask_select", _sequence("ask_select", label))
    monkeypatch.setattr(app, "ask_confirm", _sequence("ask_confirm", True))

    browser_calls = []
    monkeypatch.setattr(app.webbrowser, "open", lambda url: browser_calls.append(url))

    app.view_report_flow()

    assert len(browser_calls) == 1
    assert experiment_id in browser_calls[0]
