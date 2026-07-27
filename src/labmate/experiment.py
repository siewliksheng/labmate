"""M4: the Prelab -> Lab -> Report experiment workflow.

A stateful session layered on top of the existing single-turn specialists.
start_experiment() runs Prelab automatically -- reusing lookup_sds /
lookup_biosafety_level / search_sop_handbook, the same "found: false is
unresolved, not cleared" principle the M3 gate already enforces, just
applied here as a blocking checklist instead of a single response: Lab
cannot start until every unresolved item is explicitly acknowledged
(sign_off() refuses otherwise -- see memory.store.sign_off_experiment).

Once in Lab, ad-hoc literature/vision/safety questions still go through
agent.run() as before -- they're now automatically tagged with the active
experiment (memory.store.get_active_experiment_id) so Report can pull them
back. record_observation() is for explicit "log this value" moments and is
a separate, structured channel from that Q&A history -- matching how a
real lab notebook records deliberate entries, not a transcript of every
conversation that happened nearby.

generate_report() is a single synthesis call (no tools) over everything
accumulated for the experiment, saved locally as both Markdown and a
styled HTML page (var/reports/<experiment_id>.{md,html}, never committed
-- see reports/README.md for the one curated example kept in the repo).
Sending it anywhere external (Google Docs, email, etc.) is explicitly out
of scope here -- see reports/README.md and docs/architecture.md for why
that's a separate, explicitly-confirmed action, not something this
function does.

This module's own CLI is the scriptable subcommands (start/signoff/record/
report, each taking an explicit experiment_id -- useful for automation
and tests). The interactive, human-facing entry point is `labmate.app`
(a menu-driven terminal app built on questionary) -- it calls the same
functions defined here. An earlier plain-input()-based `wizard` subcommand
lived here too; it's been removed in favor of `labmate.app` rather than
keeping two overlapping interactive flows.
"""

import argparse
import json

from labmate.json_utils import extract_json_object
from labmate.llm_client import create_message
from labmate.memory import store
from labmate.mcp_server.tools import TOOL_SCHEMAS as _ALL_TOOLS
from labmate.mcp_server.tools import dispatch_tool
from labmate.paths import VAR_DIR
from labmate.report_render import render_report_html

PRELAB_SYSTEM_PROMPT = """\
You are running prelab safety preparation for a lab experiment the user \
is about to perform. Given the experiment description, identify every \
reagent, organism, and hazard-relevant procedure step mentioned or \
clearly implied, and look each one up using lookup_sds, \
lookup_biosafety_level, and search_sop_handbook. Do not rely on training \
knowledge for any hazard claim -- only what these tools actually return.

When you have looked up everything relevant, STOP calling tools and \
respond with ONLY strict JSON, no other text, in this exact shape:
{"required_ppe": ["..."], "items": [{"item": "<reagent/organism/procedure>", "resolved": true or false, "hazard_summary": "<what the lookup said, or 'no matching entry found'>", "source": "<tool name or null>"}], "unresolved_count": <int>}

This final checklist is your plain text response, never a tool call --\
do not pass the checklist (or any of its fields) as arguments to \
lookup_sds, lookup_biosafety_level, or search_sop_handbook. Those tools \
only accept the single lookup argument each was defined with.

A resolved: false item means no tool returned a match for it -- this is a \
real gap the user or a human safety officer must acknowledge before \
proceeding, not something you should guess about.
"""

PRELAB_TOOL_SCHEMAS = [
    t for t in _ALL_TOOLS if t["name"] in {"lookup_sds", "lookup_biosafety_level", "search_sop_handbook"}
]

REPORT_SYSTEM_PROMPT = """\
You are drafting a lab experiment report from structured session data: \
the original experiment description, the prelab safety checklist, the \
lab-phase observations recorded during the experiment, any Q&A that \
happened during the lab phase, and any safety escalations that occurred. \
Write a clear Markdown report with these sections, in this order:

1. Any escalations first, prominently, if there were any -- never bury a \
safety event under results.
2. Experiment summary (what was attempted).
3. Prelab safety checklist results (what was checked, what if anything \
required sign-off, and who signed off).
4. Observations / results, from the recorded lab observations, in order.
5. Suggested next steps -- write this section as a Markdown blockquote \
(each line starting with "> "), since it is a suggestion for the \
researcher or PI to confirm, never an instruction or a final decision, \
and the blockquote formatting is what visually distinguishes it as such.

Do not introduce any new safety claim that isn't already present in the \
checklist, escalation, or Q&A data provided -- you are synthesizing what \
already happened, not performing new safety analysis.
"""

_REFORMAT_SYSTEM_PROMPT = """\
Convert the following into strict JSON, no other text, no explanation, \
in exactly this shape:
{"required_ppe": ["..."], "items": [{"item": "...", "resolved": true or false, "hazard_summary": "...", "source": "..."}], "unresolved_count": <int>}

Preserve every item and every hazard_summary from the source text as \
faithfully as possible -- do not invent new items, do not drop any.
"""

_MAX_PRELAB_TURNS = 6


def start_experiment(description: str) -> dict:
    """Creates the experiment, sets it as active, and runs Prelab
    immediately -- matching the described flow where stating the
    experiment IS what triggers prelab prep, not a separate step.
    """
    experiment_id = store.create_experiment(description)
    checklist = run_prelab(experiment_id, description)
    return {"experiment_id": experiment_id, "checklist": checklist}


def run_prelab(experiment_id: str, description: str) -> dict:
    messages = [{"role": "user", "content": f"Experiment description: {description}"}]

    for _ in range(_MAX_PRELAB_TURNS):
        response = create_message(
            system=PRELAB_SYSTEM_PROMPT, messages=messages, tools=PRELAB_TOOL_SCHEMAS, max_tokens=1024
        )
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            text = "".join(block.text for block in response.content if block.type == "text")
            checklist = _parse_checklist_with_reformat_retry(text)
            store.save_prelab_checklist(experiment_id, checklist)
            return checklist

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            result = dispatch_tool(block.name, block.input)
            tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(result)})
        messages.append({"role": "user", "content": tool_results})

    checklist = {
        "required_ppe": [],
        "items": [],
        "unresolved_count": 1,
        "note": "prelab did not converge within the turn limit -- treat as fully unresolved, fail closed",
    }
    store.save_prelab_checklist(experiment_id, checklist)
    return checklist


def _parse_checklist_with_reformat_retry(text: str) -> dict:
    """Observed live against Ollama/llama3.1: a weaker model can produce
    plain prose instead of the requested JSON on its final turn, even with
    an explicit instruction not to. Rather than failing closed immediately,
    give it one narrower, tool-free retry -- "reformat what you just said
    as JSON" is a much easier task than "search tools AND produce JSON,"
    and removing tool access removes the main observed distraction (the
    model stuffing the checklist into a tool call instead of ending the
    turn). If the retry also fails to parse, the outcome is identical to
    not retrying at all: fail closed, fully unresolved.
    """
    try:
        return _parse_checklist_strict(text)
    except Exception:
        pass

    try:
        response = create_message(
            system=_REFORMAT_SYSTEM_PROMPT, messages=[{"role": "user", "content": text}], max_tokens=1024
        )
        retry_text = "".join(block.text for block in response.content if block.type == "text")
        return _parse_checklist_strict(retry_text)
    except Exception as exc:
        return {
            "required_ppe": [],
            "items": [],
            "unresolved_count": 1,
            "note": f"could not parse prelab checklist even after a reformat retry ({exc}) -- treat as fully unresolved, fail closed",
        }


def _parse_checklist_strict(text: str) -> dict:
    parsed = extract_json_object(text)
    parsed.setdefault("required_ppe", [])
    parsed.setdefault("items", [])
    parsed.setdefault("unresolved_count", sum(1 for item in parsed["items"] if not item.get("resolved")))
    return parsed


def sign_off(experiment_id: str, signed_off_by: str, acknowledge_unresolved: bool = False) -> dict:
    return store.sign_off_experiment(experiment_id, signed_off_by, acknowledge_unresolved)


def record_observation(experiment_id: str, kind: str, content: str, note: str | None = None) -> None:
    store.record_lab_observation(experiment_id, kind, content, note)


def generate_report(experiment_id: str) -> dict:
    data = _gather_report_data(experiment_id)

    prompt = (
        f"Experiment description: {data['experiment']['description']}\n\n"
        f"Prelab checklist:\n{json.dumps(data['prelab_checklist'], indent=2)}\n\n"
        f"Signed off by: {data['experiment']['signed_off_by']} at {data['experiment']['signed_off_at']}\n\n"
        f"Lab observations:\n{_format_observations(data['lab_observations'])}\n\n"
        f"Q&A during lab phase:\n{_format_qa(data['qa_history'])}\n\n"
        f"Escalations during this experiment:\n{_format_escalations(data['escalations'])}\n"
    )

    response = create_message(
        system=REPORT_SYSTEM_PROMPT, messages=[{"role": "user", "content": prompt}], max_tokens=2048
    )
    report_text = "".join(block.text for block in response.content if block.type == "text")

    store.mark_experiment_reported(experiment_id)
    store.set_active_experiment_id(None)
    data["experiment"]["status"] = "reported"  # reflect the just-applied update; data was fetched before it

    reports_dir = VAR_DIR / "reports"
    reports_dir.mkdir(exist_ok=True, parents=True)

    markdown_path = reports_dir / f"{experiment_id}.md"
    markdown_path.write_text(report_text, encoding="utf-8")

    html_path = reports_dir / f"{experiment_id}.html"
    html_path.write_text(render_report_html(report_text, data["experiment"]), encoding="utf-8")

    return {"markdown": str(markdown_path), "html": str(html_path)}


def _gather_report_data(experiment_id: str) -> dict:
    experiment = store.get_experiment(experiment_id)
    if experiment is None:
        raise ValueError(f"No experiment with id {experiment_id}")

    return {
        "experiment": experiment,
        "prelab_checklist": json.loads(experiment["prelab_checklist"] or "{}"),
        "lab_observations": store.get_lab_observations(experiment_id),
        "qa_history": store.get_qa_history_for_experiment(experiment_id),
        "escalations": _get_escalations_for_experiment(experiment_id),
    }


def _get_escalations_for_experiment(experiment_id: str) -> list[dict]:
    path = VAR_DIR / "escalations.jsonl"
    if not path.exists():
        return []
    escalations = [json.loads(line) for line in path.read_text(encoding="utf-8").strip().splitlines()]
    return [entry for entry in escalations if entry.get("experiment_id") == experiment_id]


def _format_observations(observations: list[dict]) -> str:
    if not observations:
        return "(none recorded)"
    return "\n".join(f"- [{o['timestamp']}] ({o['kind']}) {o['content']}" + (f" -- {o['note']}" if o['note'] else "") for o in observations)


def _format_qa(qa_history: list[dict]) -> str:
    if not qa_history:
        return "(none)"
    return "\n\n".join(f"Q ({qa['specialist']}): {qa['user_input']}\nA: {qa['response_text']}" for qa in qa_history)


def _format_escalations(escalations: list[dict]) -> str:
    if not escalations:
        return "(none)"
    return "\n".join(f"- [{e['timestamp']}] ({e['urgency']}) {e['summary']}" for e in escalations)


def _resolve_experiment_id(explicit_id: str | None) -> str:
    """signoff/record/report all default to whichever experiment is
    currently active (see memory.store.get_active_experiment_id) so a
    human doesn't have to copy an id into every command -- pass one
    explicitly only to target a different (e.g. already-closed) session.
    """
    if explicit_id:
        return explicit_id
    active = store.get_active_experiment_id()
    if active is None:
        raise SystemExit(
            "No experiment_id given and no experiment is currently active. "
            "Run `labmate.experiment start \"...\"` first, or pass an id explicitly."
        )
    return active


def format_checklist_lines(checklist: dict) -> list[str]:
    """Shared formatting for displaying a prelab checklist -- used by
    labmate.app's menu screens.
    """
    lines = []
    ppe = checklist.get("required_ppe", [])
    if ppe:
        lines.append(f"Required PPE: {', '.join(ppe)}")
    for item in checklist.get("items", []):
        mark = "[ok]" if item.get("resolved") else "[!! UNRESOLVED]"
        lines.append(f"  {mark} {item.get('item')} -- {item.get('hazard_summary')}")
    if checklist.get("note"):
        lines.append(f"  note: {checklist['note']}")
    return lines


def main():
    parser = argparse.ArgumentParser(prog="labmate.experiment")
    subparsers = parser.add_subparsers(dest="command", required=True)

    start_p = subparsers.add_parser("start", help="describe an experiment; runs prelab automatically")
    start_p.add_argument("description")

    signoff_p = subparsers.add_parser("signoff", help="sign off prelab to start lab work")
    signoff_p.add_argument("experiment_id", nargs="?", default=None, help="defaults to the active experiment")
    signoff_p.add_argument("--by", required=True)
    signoff_p.add_argument("--acknowledge-unresolved", action="store_true")

    record_p = subparsers.add_parser("record", help="log a lab observation (text or image)")
    record_p.add_argument("experiment_id", nargs="?", default=None, help="defaults to the active experiment")
    record_p.add_argument("--kind", choices=["text", "image"], required=True)
    record_p.add_argument("--content", required=True)
    record_p.add_argument("--note", default=None)

    report_p = subparsers.add_parser("report", help="generate the report (Markdown + HTML)")
    report_p.add_argument("experiment_id", nargs="?", default=None, help="defaults to the active experiment")

    args = parser.parse_args()

    if args.command == "start":
        print(json.dumps(start_experiment(args.description), indent=2))
    elif args.command == "signoff":
        experiment_id = _resolve_experiment_id(args.experiment_id)
        print(json.dumps(sign_off(experiment_id, args.by, args.acknowledge_unresolved), indent=2))
    elif args.command == "record":
        experiment_id = _resolve_experiment_id(args.experiment_id)
        record_observation(experiment_id, args.kind, args.content, args.note)
        print("recorded")
    elif args.command == "report":
        experiment_id = _resolve_experiment_id(args.experiment_id)
        paths = generate_report(experiment_id)
        print(f"Report saved to:\n  {paths['markdown']}\n  {paths['html']}")


if __name__ == "__main__":
    main()
