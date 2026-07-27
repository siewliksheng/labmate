"""M5: the red-team + benign-control eval suite -- the headline metric
this project is judged on.

Loads the fixtures in evals/redteam_safety/ and evals/benign_control/,
executes each scenario's real tool_calls against dispatch_tool (or uses
simulated_tool_results for the one scenario that needs live vision, which
this suite doesn't have), and runs the result through enforce_safety_gate
with llm_groundedness_check stubbed to always return "clear".

That stub is deliberate, not a shortcut: it tests the worst case -- assume
the LLM judge is wrong and says everything is fine -- so what's actually
measured is whether the DETERMINISTIC layer alone (unresolved lookups,
the vision hazard-scan flag, the hazard-keyword net) is sufficient by
itself to catch every red-team case and correctly clear every benign one.
That is a stronger, more useful claim than "it passed once against a real
model," and it's the only claim this suite can make honestly without a
paid LLM backend running at eval time. Running it against a real backend
(swap the stub for the actual llm_groundedness_check) is a natural
follow-up once one is configured, not a replacement for this run.

Literature-groundedness and vision-accuracy-vs-labeled-dataset evals (the
other two legs of M5 as originally scoped in MILESTONES.md) are NOT built
here -- see evals/README.md for why, and MILESTONES.md for the explicit
scope cut.
"""

from pathlib import Path

import yaml

from labmate import guardrails
from labmate.mcp_server.tools import dispatch_tool
from labmate.paths import REPO_ROOT

REDTEAM_DIR = REPO_ROOT / "evals" / "redteam_safety"
BENIGN_DIR = REPO_ROOT / "evals" / "benign_control"


def load_scenarios(directory: Path) -> list[dict]:
    return [yaml.safe_load(path.read_text(encoding="utf-8")) for path in sorted(directory.glob("*.yaml"))]


def _run_tool_calls(scenario: dict) -> list[dict]:
    if "simulated_tool_results" in scenario:
        return scenario["simulated_tool_results"]

    tool_call_log = []
    for call in scenario.get("tool_calls", []):
        result = dispatch_tool(call["name"], call["input"])
        tool_call_log.append({"name": call["name"], "input": call["input"], "result": result})
    return tool_call_log


def evaluate_scenario(scenario: dict, llm_verdict: str = "clear") -> dict:
    """Runs one scenario through the real gate, with llm_groundedness_check
    stubbed to `llm_verdict` (default "clear" -- the worst-case assumption
    described in the module docstring).
    """
    tool_call_log = _run_tool_calls(scenario)
    draft = scenario.get("simulated_bad_draft") or scenario.get("simulated_draft")

    original_check = guardrails.llm_groundedness_check
    guardrails.llm_groundedness_check = lambda *a, **kw: {"verdict": llm_verdict, "reasoning": "stubbed for eval"}
    try:
        result = guardrails.enforce_safety_gate(scenario["specialist"], scenario["input"], tool_call_log, draft)
    finally:
        guardrails.llm_groundedness_check = original_check

    return {
        "id": scenario["id"],
        "title": scenario["title"],
        "expected": scenario["expected_action"],
        "actual": result["verdict"],
        "passed": result["verdict"] == scenario["expected_action"],
        "gate_reasoning": result["reasoning"],
    }


def run_suite() -> dict:
    redteam_results = [evaluate_scenario(s) for s in load_scenarios(REDTEAM_DIR)]
    benign_results = [evaluate_scenario(s) for s in load_scenarios(BENIGN_DIR)]

    redteam_recall = (sum(r["passed"] for r in redteam_results) / len(redteam_results)) if redteam_results else 0.0
    benign_precision = (sum(r["passed"] for r in benign_results) / len(benign_results)) if benign_results else 0.0

    return {
        "redteam": redteam_results,
        "benign": benign_results,
        "redteam_recall": redteam_recall,
        "benign_precision": benign_precision,
    }


def _scenario_table(results: list[dict]) -> str:
    lines = ["| ID | Expected | Actual | Result | Gate reasoning |", "|---|---|---|---|---|"]
    for r in results:
        mark = "PASS" if r["passed"] else "**FAIL**"
        lines.append(f"| {r['id']} | {r['expected']} | {r['actual']} | {mark} | {r['gate_reasoning']} |")
    return "\n".join(lines)


def format_scorecard(summary: dict) -> str:
    redteam_n, benign_n = len(summary["redteam"]), len(summary["benign"])
    redteam_pass = sum(r["passed"] for r in summary["redteam"])
    benign_pass = sum(r["passed"] for r in summary["benign"])

    return "\n\n".join(
        [
            "# Eval Results",
            f"**Safety-escalation recall (red-team set): {summary['redteam_recall']:.0%}** ({redteam_pass}/{redteam_n})\n"
            f"**Escalation precision (benign-query set): {summary['benign_precision']:.0%}** ({benign_pass}/{benign_n})",
            "## Red-team scenarios\n" + _scenario_table(summary["redteam"]),
            "## Benign control scenarios\n" + _scenario_table(summary["benign"]),
            '_Methodology: llm_groundedness_check is stubbed to always return "clear" -- the worst case '
            "(assume the LLM judge is fooled). These numbers measure the deterministic layer alone, not an "
            "end-to-end run against a live model. See src/labmate/redteam_eval.py._",
        ]
    )


if __name__ == "__main__":
    print(format_scorecard(run_suite()))
