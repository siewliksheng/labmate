"""A local FastAPI website -- the same underlying labmate.experiment /
labmate.review_queue functions labmate.app's terminal menus call, through
a browser instead. Built after trying the terminal app and clarifying the
actual preference was a website. Both interfaces stay: app.py already
works and is tested; this becomes the new recommended default, not a
replacement forced by a flaw in the other one.

Plain server-rendered HTML forms, no JS framework -- a step-by-step
wizard flow doesn't need one, and every POST redirects (303) back to a
GET that re-reads state from SQLite (store.py), so there's no server-side
session state to manage beyond what's already persisted there.

The "active experiment" side-channel (memory.store.get_active_experiment_id,
see docs/architecture.md's M4 notes) was designed for a single-session CLI
where there's only ever one "current" experiment. A website can have
several experiment pages open by URL at once, so every route that needs
ad-hoc Q&A tagged correctly explicitly sets the active pointer to the
URL's experiment_id first, rather than trusting whatever was last active
globally -- see ask_question() below. This is a real, documented
limitation of that side channel under concurrent use, not fixed here,
just worked around per-request for the common single-user case.
"""

import json
from pathlib import Path

from fastapi import FastAPI, Form
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from labmate import experiment, review_queue
from labmate.memory import store
from labmate.paths import VAR_DIR

app = FastAPI(title="LabMate")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(
        request, "index.html", {"pending_count": len(review_queue.list_pending())}
    )


@app.get("/experiments/new", response_class=HTMLResponse)
def new_experiment_form(request: Request):
    return templates.TemplateResponse(request, "experiment_new.html", {})


@app.post("/experiments/new")
def create_experiment(description: str = Form(...)):
    result = experiment.start_experiment(description)
    return RedirectResponse(f"/experiments/{result['experiment_id']}/prelab", status_code=303)


@app.get("/experiments/{experiment_id}/prelab", response_class=HTMLResponse)
def prelab_page(request: Request, experiment_id: str):
    exp = store.get_experiment(experiment_id)
    if exp is None:
        return HTMLResponse("Experiment not found", status_code=404)

    checklist = json.loads(exp["prelab_checklist"] or "{}")
    unresolved_count = sum(1 for item in checklist.get("items", []) if not item.get("resolved"))
    return templates.TemplateResponse(
        request, "prelab.html", {"experiment": exp, "checklist": checklist, "unresolved_count": unresolved_count}
    )


@app.post("/experiments/{experiment_id}/signoff")
def signoff(experiment_id: str, signed_off_by: str = Form(...), acknowledge_unresolved: str | None = Form(None)):
    experiment.sign_off(experiment_id, signed_off_by, acknowledge_unresolved=bool(acknowledge_unresolved))
    # Re-fetching inside prelab_page shows the outcome either way: still
    # "prelab_ready" (blocked, form re-shown) or now "lab" (link to Lab).
    return RedirectResponse(f"/experiments/{experiment_id}/prelab", status_code=303)


@app.get("/experiments/{experiment_id}/lab", response_class=HTMLResponse)
def lab_page(request: Request, experiment_id: str):
    exp = store.get_experiment(experiment_id)
    if exp is None:
        return HTMLResponse("Experiment not found", status_code=404)
    return templates.TemplateResponse(
        request,
        "lab.html",
        {
            "experiment": exp,
            "qa_history": store.get_qa_history_for_experiment(experiment_id),
            "observations": store.get_lab_observations(experiment_id),
        },
    )


@app.post("/experiments/{experiment_id}/lab/ask")
def ask_question(experiment_id: str, question: str = Form(...)):
    from labmate.agent import run as agent_run

    store.set_active_experiment_id(experiment_id)  # see module docstring
    agent_run(question)
    return RedirectResponse(f"/experiments/{experiment_id}/lab", status_code=303)


@app.post("/experiments/{experiment_id}/lab/record")
def record(experiment_id: str, kind: str = Form(...), content: str = Form(...), note: str | None = Form(None)):
    experiment.record_observation(experiment_id, kind, content, note or None)
    return RedirectResponse(f"/experiments/{experiment_id}/lab", status_code=303)


@app.post("/experiments/{experiment_id}/report")
def make_report(experiment_id: str):
    experiment.generate_report(experiment_id)
    return RedirectResponse(f"/experiments/{experiment_id}/report", status_code=303)


@app.get("/experiments/{experiment_id}/report")
def report_page(experiment_id: str):
    html_path = VAR_DIR / "reports" / f"{experiment_id}.html"
    if not html_path.exists():
        return RedirectResponse(f"/experiments/{experiment_id}/lab", status_code=303)
    return FileResponse(html_path)


@app.get("/escalations", response_class=HTMLResponse)
def escalations_page(request: Request):
    return templates.TemplateResponse(request, "escalations.html", {"pending": review_queue.list_pending()})


@app.post("/escalations/{index}/resolve")
def resolve_escalation(index: int, decision: str = Form(...), resolved_by: str = Form(...), note: str | None = Form(None)):
    review_queue.resolve(index, decision, resolved_by, note or None)
    return RedirectResponse("/escalations", status_code=303)


@app.get("/reports", response_class=HTMLResponse)
def reports_page(request: Request):
    return templates.TemplateResponse(request, "reports_list.html", {"experiments": store.list_experiments()})


def main():
    import webbrowser

    import uvicorn

    webbrowser.open("http://127.0.0.1:8000")
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
