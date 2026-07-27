"""CI's actual regression gate on the headline metric -- see
labmate.redteam_eval's module docstring for exactly what these numbers do
and don't claim (deterministic-layer-only, LLM check stubbed to the worst
case, since no paid backend runs in CI).
"""

from labmate.redteam_eval import run_suite


def test_redteam_recall_is_100_percent():
    summary = run_suite()
    failures = [r for r in summary["redteam"] if not r["passed"]]
    assert not failures, f"red-team recall regression: {failures}"


def test_benign_control_does_not_false_escalate():
    summary = run_suite()
    failures = [r for r in summary["benign"] if not r["passed"]]
    assert not failures, f"benign-control false escalation(s): {failures}"
