"""A menu-driven terminal app tying together the Prelab -> Lab -> Report
workflow (labmate.experiment) and the escalation review queue
(labmate.review_queue) into one entry point with arrow-key select menus
and step-by-step screens, instead of typed free-text commands.

Supersedes experiment.py's old plain-input()-based `wizard` subcommand --
replaced rather than kept alongside, since a second, mostly-overlapping
interactive flow would just be confusing. The scriptable subcommands
(start/signoff/record/report in labmate.experiment) are unaffected and
still the right tool for automation.

Built on questionary (prompt_toolkit under the hood) -- a real terminal
app, not a browser page, per the interface decision made when this was
scoped. Every menu/prompt function here is a thin wrapper so the flow
functions below can be tested by monkeypatching a single call site per
question, rather than mocking questionary's Question/`.ask()` protocol
directly in every test.
"""

import webbrowser

import questionary

from labmate import experiment, review_queue
from labmate.memory import store
from labmate.paths import VAR_DIR

MAIN_MENU_CHOICES = [
    "Start a new experiment",
    "Resolve a pending escalation",
    "View a past report",
    "Quit",
]


def ask_select(message: str, choices: list[str]) -> str | None:
    return questionary.select(message, choices=choices).ask()


def ask_text(message: str) -> str | None:
    return questionary.text(message).ask()


def ask_confirm(message: str, default: bool = False) -> bool | None:
    return questionary.confirm(message, default=default).ask()


_ANSI_CODES = {"fg:ansigreen": "\033[32m", "fg:ansiyellow": "\033[33m", "fg:ansired": "\033[31m"}
_ANSI_RESET = "\033[0m"


def say(message: str, style: str | None = None) -> None:
    # Plain print + raw ANSI codes rather than questionary.print(): the
    # latter goes through prompt_toolkit's full output-detection stack,
    # which can fail outside a native console (observed under a git-bash/
    # mintty shell without a real Win32 console handle) even though the
    # actual select/text/confirm prompts work fine there.
    code = _ANSI_CODES.get(style, "")
    print(f"{code}{message}{_ANSI_RESET}" if code else message)


def main() -> None:
    while True:
        choice = ask_select("What would you like to do?", MAIN_MENU_CHOICES)
        if choice is None or choice == "Quit":
            return
        if choice == "Start a new experiment":
            run_experiment_flow()
        elif choice == "Resolve a pending escalation":
            resolve_escalation_flow()
        elif choice == "View a past report":
            view_report_flow()


def run_experiment_flow() -> None:
    description = ask_text("What experiment do you want to run?")
    if not description:
        return

    say("\nRunning prelab safety checks (real SDS/biosafety/SOP lookups)...\n")
    result = experiment.start_experiment(description)
    experiment_id = result["experiment_id"]
    checklist = result["checklist"]
    for line in experiment.format_checklist_lines(checklist):
        print(line)

    who = ask_text("Your name (for sign-off):") or "unspecified"
    unresolved = [item for item in checklist.get("items", []) if not item.get("resolved")]

    if unresolved:
        ack = ask_confirm(f"{len(unresolved)} item(s) are unresolved. Acknowledge and proceed anyway?", default=False)
        if not ack:
            say(
                f"Not signed off. Resume later with:\n"
                f'  python -m labmate.experiment signoff {experiment_id} --by "{who}" --acknowledge-unresolved',
                style="fg:ansiyellow",
            )
            return
        experiment.sign_off(experiment_id, who, acknowledge_unresolved=True)
    else:
        experiment.sign_off(experiment_id, who)

    say(f"\nSigned off -- experiment {experiment_id} is now in Lab phase.\n", style="fg:ansigreen")
    _lab_phase_loop(experiment_id)

    say("\nGenerating report...")
    paths = experiment.generate_report(experiment_id)
    say(f"\nReport saved:\n  {paths['markdown']}\n  {paths['html']}", style="fg:ansigreen")

    if ask_confirm("Open the HTML report in your browser?", default=True):
        webbrowser.open(f"file://{paths['html']}")


def _lab_phase_loop(experiment_id: str) -> None:
    from labmate.agent import run as agent_run

    lab_choices = ["Ask a question", "Record a text observation", "Record an image observation", "Finish and generate report"]

    while True:
        action = ask_select("Lab phase -- what next?", lab_choices)
        if action is None or action == "Finish and generate report":
            return
        if action == "Ask a question":
            question = ask_text("Your question:")
            if question:
                print(agent_run(question))
        elif action == "Record a text observation":
            content = ask_text("What did you observe?")
            if content:
                note = ask_text("Note (optional, press enter to skip):")
                experiment.record_observation(experiment_id, "text", content, note or None)
                say("Recorded.", style="fg:ansigreen")
        elif action == "Record an image observation":
            path = ask_text("Path to the image:")
            if path:
                note = ask_text("Note (optional, press enter to skip):")
                experiment.record_observation(experiment_id, "image", path, note or None)
                say("Recorded.", style="fg:ansigreen")


def resolve_escalation_flow() -> None:
    pending = review_queue.list_pending()
    if not pending:
        say("No pending escalations.")
        return

    labels = [f"[{i}] {e['timestamp']}  ({e['urgency']})  {e['summary'][:80]}" for i, e in enumerate(pending, start=1)]
    picked = ask_select("Select an escalation to resolve:", labels + ["Cancel"])
    if picked is None or picked == "Cancel":
        return
    index = int(picked.split("]")[0][1:])

    decision = ask_select("Decision:", ["confirmed_hazard", "false_positive", "Cancel"])
    if decision is None or decision == "Cancel":
        return

    by = ask_text("Your name:") or "unspecified"
    note = ask_text("Note (optional, press enter to skip):")

    result = review_queue.resolve(index, decision, by, note or None)
    say(str(result), style="fg:ansigreen" if result["resolved"] else "fg:ansired")


def view_report_flow() -> None:
    experiments = store.list_experiments()
    if not experiments:
        say("No experiments yet.")
        return

    labels = [f"{e['id']}  [{e['status']}]  {e['description'][:70]}" for e in experiments]
    picked = ask_select("Select an experiment:", labels + ["Cancel"])
    if picked is None or picked == "Cancel":
        return
    experiment_id = picked.split(" ", 1)[0]

    html_path = VAR_DIR / "reports" / f"{experiment_id}.html"
    md_path = VAR_DIR / "reports" / f"{experiment_id}.md"

    if not html_path.exists() and not md_path.exists():
        say(f"No report generated yet for {experiment_id}.", style="fg:ansiyellow")
        return

    say(f"Markdown: {md_path}\nHTML: {html_path}", style="fg:ansigreen")
    if html_path.exists() and ask_confirm("Open in browser?", default=True):
        webbrowser.open(f"file://{html_path}")


if __name__ == "__main__":
    main()
