import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from labmate import experiment, review_queue, web
from labmate.memory import store


@pytest.fixture(autouse=True)
def isolated_var_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "VAR_DIR", tmp_path)
    monkeypatch.setattr(experiment, "VAR_DIR", tmp_path)
    monkeypatch.setattr(web, "VAR_DIR", tmp_path)
    monkeypatch.setattr(review_queue, "VAR_DIR", tmp_path)
    import labmate.mcp_server.tools as tools_module

    monkeypatch.setattr(tools_module, "VAR_DIR", tmp_path)


@pytest.fixture
def client():
    return TestClient(web.app)


def _fake_llm(text: str):
    def _call(system, messages, tools=None, max_tokens=2048):
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], stop_reason="end_turn")

    return _call


def test_home_page_loads(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Start a new experiment" in response.text


def test_create_experiment_rejects_blank_description_without_calling_llm(client, monkeypatch):
    def _boom(*_args, **_kwargs):
        raise AssertionError("create_message should never be called for a blank description")

    monkeypatch.setattr(experiment, "create_message", _boom)

    response = client.post("/experiments/new", data={"description": "   "})

    assert response.status_code == 400
    assert "cannot be empty" in response.text
    assert store.list_experiments() == []


def test_create_experiment_redirects_to_prelab(client, monkeypatch):
    checklist = {"required_ppe": [], "items": [], "unresolved_count": 0}
    monkeypatch.setattr(experiment, "create_message", _fake_llm(json.dumps(checklist)))

    response = client.post("/experiments/new", data={"description": "Simple experiment"}, follow_redirects=False)

    assert response.status_code == 303
    assert "/prelab" in response.headers["location"]

    prelab_response = client.get(response.headers["location"])
    assert prelab_response.status_code == 200
    assert "Simple experiment" in prelab_response.text


def test_signoff_blocked_when_unresolved_not_acknowledged(client, monkeypatch):
    checklist = {
        "required_ppe": [],
        "items": [{"item": "mystery reagent", "resolved": False, "hazard_summary": "no matching entry found"}],
        "unresolved_count": 1,
    }
    monkeypatch.setattr(experiment, "create_message", _fake_llm(json.dumps(checklist)))
    result = experiment.start_experiment("Mystery reagent experiment")
    experiment_id = result["experiment_id"]

    response = client.post(f"/experiments/{experiment_id}/signoff", data={"signed_off_by": "alex"}, follow_redirects=False)
    assert response.status_code == 303

    prelab_response = client.get(f"/experiments/{experiment_id}/prelab")
    assert "must be acknowledged" in prelab_response.text
    exp = store.get_experiment(experiment_id)
    assert exp["status"] == "prelab_ready"


def test_signoff_with_acknowledgement_proceeds_to_lab(client, monkeypatch):
    checklist = {
        "required_ppe": [],
        "items": [{"item": "mystery reagent", "resolved": False, "hazard_summary": "no matching entry found"}],
        "unresolved_count": 1,
    }
    monkeypatch.setattr(experiment, "create_message", _fake_llm(json.dumps(checklist)))
    result = experiment.start_experiment("Mystery reagent experiment")
    experiment_id = result["experiment_id"]

    client.post(
        f"/experiments/{experiment_id}/signoff",
        data={"signed_off_by": "alex", "acknowledge_unresolved": "yes"},
        follow_redirects=False,
    )

    exp = store.get_experiment(experiment_id)
    assert exp["status"] == "lab"


def test_record_observation_appears_in_lab_history(client, monkeypatch):
    checklist = {"required_ppe": [], "items": [], "unresolved_count": 0}
    monkeypatch.setattr(experiment, "create_message", _fake_llm(json.dumps(checklist)))
    result = experiment.start_experiment("Simple experiment")
    experiment_id = result["experiment_id"]
    experiment.sign_off(experiment_id, "alex")

    client.post(
        f"/experiments/{experiment_id}/lab/record",
        data={"kind": "text", "content": "OD600 = 0.42", "note": "flask A"},
        follow_redirects=False,
    )

    lab_response = client.get(f"/experiments/{experiment_id}/lab")
    assert "OD600 = 0.42" in lab_response.text
    assert "flask A" in lab_response.text


def test_ask_question_tags_qa_to_the_url_experiment_not_whatever_is_globally_active(client, monkeypatch):
    checklist = {"required_ppe": [], "items": [], "unresolved_count": 0}
    monkeypatch.setattr(experiment, "create_message", _fake_llm(json.dumps(checklist)))

    result_a = experiment.start_experiment("Experiment A")
    experiment.sign_off(result_a["experiment_id"], "alex")

    result_b = experiment.start_experiment("Experiment B")  # this becomes the globally "active" one
    experiment.sign_off(result_b["experiment_id"], "alex")

    import labmate.agent as agent_module

    monkeypatch.setattr(agent_module, "create_message", _fake_llm("Here's an answer."))
    monkeypatch.setattr(
        agent_module,
        "enforce_safety_gate",
        lambda specialist_name, user_input, tool_call_log, draft_text: {
            "verdict": "clear",
            "response_text": draft_text,
            "reasoning": "test",
        },
    )

    # Ask a question on experiment A's page, even though B is globally active.
    client.post(f"/experiments/{result_a['experiment_id']}/lab/ask", data={"question": "what's new?"}, follow_redirects=False)

    qa_for_a = store.get_qa_history_for_experiment(result_a["experiment_id"])
    qa_for_b = store.get_qa_history_for_experiment(result_b["experiment_id"])
    assert len(qa_for_a) == 1
    assert len(qa_for_b) == 0


def test_full_report_flow_serves_generated_html(client, monkeypatch):
    checklist = {"required_ppe": [], "items": [], "unresolved_count": 0}
    monkeypatch.setattr(experiment, "create_message", _fake_llm(json.dumps(checklist)))
    result = experiment.start_experiment("Simple experiment")
    experiment_id = result["experiment_id"]
    experiment.sign_off(experiment_id, "alex")

    monkeypatch.setattr(experiment, "create_message", _fake_llm("# Report\n\nAll done."))
    response = client.post(f"/experiments/{experiment_id}/report", follow_redirects=False)
    assert response.status_code == 303

    report_response = client.get(f"/experiments/{experiment_id}/report")
    assert report_response.status_code == 200
    assert "All done" in report_response.text


def test_escalations_page_lists_pending(client):
    from labmate.mcp_server.tools import dispatch_tool

    dispatch_tool("escalate_to_safety_officer", {"summary": "needs human review", "urgency": "urgent"})

    response = client.get("/escalations")
    assert "needs human review" in response.text


def test_resolve_escalation_via_form(client):
    from labmate.mcp_server.tools import dispatch_tool

    dispatch_tool("escalate_to_safety_officer", {"summary": "needs human review", "urgency": "urgent"})

    response = client.post(
        "/escalations/1/resolve",
        data={"decision": "confirmed_hazard", "resolved_by": "dr. lin", "note": "verified"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert review_queue.list_pending() == []


def test_reports_page_lists_experiments(client, monkeypatch):
    checklist = {"required_ppe": [], "items": [], "unresolved_count": 0}
    monkeypatch.setattr(experiment, "create_message", _fake_llm(json.dumps(checklist)))
    experiment.start_experiment("Findable experiment")

    response = client.get("/reports")
    assert "Findable experiment" in response.text
