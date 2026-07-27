"""M5: the human review queue for escalations.

escalate_to_safety_officer (M1) already logs every escalation as a
status: "pending" entry in var/escalations.jsonl. This module is the
other half: listing what's pending, and letting a human resolve one.

CLI-based, consistent with the interface decision already made for M4
(a friendlier CLI over a web UI) -- not because a web UI wouldn't be a
reasonable upgrade later (see docs/architecture.md).

Resolving an entry updates it in place in escalations.jsonl -- the same
store IS the memory here, matching M2's "write everything, retrieval
handled at read time" policy applied to this data too. A "false_positive"
resolution is a real signal that the deterministic hazard-keyword net (or
the LLM check) over-fired; promoting it into evals/benign_control/ as a
new precision-eval case is a human curation decision, deliberately not
automated here.
"""

import argparse
import json
from datetime import datetime, timezone

from labmate.paths import VAR_DIR

_ESCALATIONS_FILE = "escalations.jsonl"


def _read_all() -> list[dict]:
    path = VAR_DIR / _ESCALATIONS_FILE
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").strip().splitlines() if line.strip()]


def _write_all(entries: list[dict]) -> None:
    path = VAR_DIR / _ESCALATIONS_FILE
    with path.open("w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")


def list_pending() -> list[dict]:
    return [entry for entry in _read_all() if entry.get("status") == "pending"]


def resolve(index: int, decision: str, resolved_by: str, note: str | None = None) -> dict:
    """`index` is the 1-based position within the CURRENT list_pending()
    result, matching what the CLI's `list` command just printed -- not a
    stable id (escalations.jsonl entries don't have one). Always re-run
    `list` before resolving if anything else may have changed in between.
    """
    entries = _read_all()
    pending_positions = [i for i, entry in enumerate(entries) if entry.get("status") == "pending"]

    if not (1 <= index <= len(pending_positions)):
        return {"resolved": False, "note": f"No pending escalation at index {index} (there are {len(pending_positions)})."}

    target = pending_positions[index - 1]
    entries[target].update(
        {
            "status": "resolved",
            "decision": decision,
            "resolved_by": resolved_by,
            "resolved_at": datetime.now(timezone.utc).isoformat(),
            "resolution_note": note,
        }
    )
    _write_all(entries)
    return {"resolved": True, "entry": entries[target]}


def main():
    parser = argparse.ArgumentParser(prog="labmate.review_queue")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list", help="show pending escalations")

    resolve_p = subparsers.add_parser("resolve", help="resolve a pending escalation")
    resolve_p.add_argument("index", type=int, help="1-based index from the most recent `list`")
    resolve_p.add_argument("--decision", choices=["confirmed_hazard", "false_positive"], required=True)
    resolve_p.add_argument("--by", required=True)
    resolve_p.add_argument("--note", default=None)

    args = parser.parse_args()

    if args.command == "list":
        pending = list_pending()
        if not pending:
            print("No pending escalations.")
            return
        for i, entry in enumerate(pending, start=1):
            exp = entry.get("experiment_id") or "(no active experiment)"
            print(f"[{i}] {entry['timestamp']}  urgency={entry['urgency']}  experiment={exp}")
            print(f"    {entry['summary'][:220]}")
    elif args.command == "resolve":
        print(json.dumps(resolve(args.index, args.decision, args.by, args.note), indent=2))


if __name__ == "__main__":
    main()
