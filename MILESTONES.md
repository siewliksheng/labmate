# Milestones

Each milestone lands one concept from the agentic-AI-engineering roadmap, on
the same codebase, in order. This file plus the git history is the actual
portfolio artifact — not just whatever the code looks like at the end.

- [x] **M0 — Bare loop + hardcoded routing** _(harness, seed)_
      One Anthropic Messages-API loop, shared by all specialists. Routing is
      a hardcoded keyword check. No tools yet — specialists answer from the
      model's own knowledge and are explicitly told to disclaim that.
- [x] **M1 — Real tools + tracing** _(tool design, observability)_
      `search_pubmed` + `fetch_abstract` (NCBI E-utilities), `search_biorxiv`
      (Europe PMC, scoped to preprint servers), `analyze_image` (two-pass
      Claude vision), `lookup_sds` (PubChem GHS), `lookup_biosafety_level`
      (curated local table), `escalate_to_safety_officer` (local review
      queue, `var/escalations.jsonl`). Every call gets an OTel span —
      exports to Langfuse if credentials are set, otherwise falls back to
      `var/spans.jsonl` so tracing is provably working with zero external
      accounts. All non-network behavior + the live network calls are
      covered by `tests/test_tools.py` (network cases marked `@pytest.mark.network`).
- [x] **M2 — Lab memory** _(context engineering, memory)_
      `search_past_qa`, `search_past_image_analyses`, `search_sop_handbook`,
      `log_environmental_state` / `get_environmental_state` — SQLite locally
      (`var/labmate_memory.db`) rather than the Postgres/pgvector named as
      the eventual production backend, and keyword (SQL `LIKE`) retrieval
      rather than embeddings, since neither swap is justified yet (see
      `labmate/memory/store.py`). Every completed exchange and every image
      analysis is recorded automatically — no model-decided write policy.
      Environmental state entries expire (`ttl_hours`); an expired or
      never-logged entry reads as `found: false`, never as "still safe."
      The SOP handbook (`memory/data/sop_handbook/*.md`) is hand-authored
      and directly grounds 3 of the 5 red-team scenarios. Covered by
      `tests/test_memory.py` (11 tests, no network required).
- [x] **M3 — The safety gate** _(guardrails, permissions)_
      `enforce_safety_gate` wraps every specialist's draft response —
      literature and vision included, not just the safety specialist.
      Two independent checks, either flags escalation: (1) deterministic —
      any tool result this turn came back `found: false` and wasn't
      followed by an actual escalation (fires with **zero LLM calls**,
      proven live against a real unresolved PubChem lookup), or a hazard
      keyword in the draft text; (2) an LLM groundedness check that fails
      **closed** to escalate on any error (no backend configured, parse
      failure, network error). No specialist other than `safety` even
      *has* the `escalate_to_safety_officer` tool in its own schema — only
      the gate itself can invoke it on a specialist's behalf, which is the
      real (if informal) permission boundary at this milestone; a formal
      declarative policy engine is M7's job, not claimed here.
      Also added `labmate/llm_client.py` — a pluggable backend
      (`LLM_BACKEND=anthropic|ollama`) so the gate's LLM call, and the
      whole tool-calling loop, can run against a local Ollama model for
      $0 during development. Honest tradeoff documented in its module
      docstring: real for exercising harness mechanics, weaker for actual
      safety-reasoning quality. Covered by `tests/test_guardrails.py`
      (8 tests, no network or API key required — the LLM check is
      monkeypatched, proving the deterministic layer stands on its own).
- [x] **M4 — Experiment sessions: Prelab → Lab → Report** _(orchestration, memory, HITL)_
      A stateful workflow layered on the existing specialists:
      `start_experiment` states an experiment and immediately runs Prelab
      (real `lookup_sds`/`lookup_biosafety_level`/`search_sop_handbook`
      calls), producing a blocking checklist — `sign_off` mechanically
      refuses to enter Lab while any item is unresolved unless a human
      explicitly acknowledges it, the same fail-closed shape as the M3
      gate applied to a phase transition instead of a single response.
      Lab reuses the existing specialists for ad-hoc questions
      (auto-tagged to whichever experiment is active via a side-channel
      pointer, not a threaded parameter) plus a new `record_observation`
      for explicit text/image value logging, distinct from the general
      vision auto-log. `generate_report` is a single synthesis call over
      everything accumulated — escalations surfaced first, next-step
      guidance framed as a suggestion — saved locally as Markdown
      (`var/reports/`, never committed). Deliberately does **not** send
      the report anywhere external (see `reports/README.md` — Google
      Docs needs the user's own OAuth setup and any external send should
      require explicit per-run confirmation, matching how this project
      treats every other side-effecting action). One curated example,
      built from genuine PubChem/biosafety-table lookups with one real
      unresolved item, is committed at `reports/example_report.{md,html}`
      and was also rendered live as an HTML Artifact. Covered by
      `tests/test_experiment.py` (6 tests, no network or API key
      required — the LLM synthesis calls are monkeypatched).

      **Interface pass**, after the first user walkthrough of the CLI
      surfaced it as too raw: `labmate/report_render.py` renders every
      report as styled HTML (`var/reports/<id>.html`) alongside the
      Markdown, not just this one hand-built demo — generic Markdown→HTML
      via `python-markdown`, deliberately not bespoke per-field widgets,
      since that would be fragile against whatever exact wording the
      model produces (blockquotes get an "advisory" callout treatment
      because `REPORT_SYSTEM_PROMPT` asks for Suggested Next Steps to be
      written as one). `signoff`/`record`/`report` now default their
      `experiment_id` to whichever experiment is active, so a human never
      has to copy one between commands. Added a `wizard` subcommand — a
      guided, interactive walkthrough for a human at a terminal — as the
      recommended entry point, alongside the original scriptable
      subcommands. (Superseded by `labmate/app.py` — see the M5 interface
      pass below.)
- [x] **M5 — Eval suite + review queue** _(evals, HITL)_
      `labmate/redteam_eval.py` runs the 5 red-team + 5 benign-control
      scenarios through the real `enforce_safety_gate`, with real
      `lookup_sds`/`lookup_biosafety_level`/`search_sop_handbook` calls
      where applicable, and `llm_groundedness_check` stubbed to always
      return `"clear"` — the worst case, testing whether the
      **deterministic layer alone** catches everything with no model in
      the loop. Current result (`evals/results.md`): **100% recall, 100%
      precision**, both earned honestly — building this suite *found and
      fixed two real gaps*: `guardrails._vision_hazard_flagged` (the
      vision hazard-scan pass routing to the gate, promised in M1's
      docs/architecture.md but never actually wired in) and a reasoning-
      attribution bug where a "clear" LLM verdict's own text leaked
      through as the escalation reason when the deterministic check was
      what actually fired. `tests/test_redteam_evals.py` is the real CI
      regression gate (already runs as part of the existing unit-test
      step, not a separate one). `labmate/review_queue.py` adds
      `list_pending()`/`resolve()` — CLI-based per the M4 interface
      decision — resolving updates the escalation in place in
      `var/escalations.jsonl`; a `false_positive` resolution is flagged as
      a manual-curation candidate for `evals/benign_control/`, not
      auto-promoted. **Not built**: literature-groundedness and vision-
      accuracy-vs-labeled-dataset evals (need volume LLM calls or a real
      dataset download — see `evals/README.md`, explicit scope cut, not
      silently dropped). Covered by `tests/test_redteam_evals.py` (2
      tests) and `tests/test_review_queue.py` (5 tests), all offline.

      **Interface pass**, after the user asked for something more
      app-like than typed CLI commands — "select and step by step,"
      explicitly not a browser page: `labmate/app.py` is a menu-driven
      terminal app (arrow-key select menus, via `questionary`) tying
      together the M4 workflow and the M5 review queue into one entry
      point (Start a new experiment / Resolve a pending escalation / View
      a past report / Quit). **Supersedes** the M4 `wizard` subcommand
      outright rather than keeping two overlapping interactive flows —
      `experiment.py`'s scriptable subcommands are unaffected. Every menu
      question is a thin named wrapper (`ask_select`/`ask_text`/
      `ask_confirm`) specifically so flow logic can be tested by
      monkeypatching one call site per question, without mocking
      questionary's `Question`/`.ask()` protocol directly. Found and
      fixed a real portability issue while building it:
      `questionary.print()` goes through `prompt_toolkit`'s full output-
      detection stack and threw `NoConsoleScreenBufferError` under a
      git-bash/mintty shell without a native Win32 console handle, even
      though the actual `select`/`text`/`confirm` prompts work fine
      there — replaced with plain `print()` + raw ANSI codes for the
      `say()` helper. Covered by `tests/test_app.py` (4 tests, all
      offline, real SQLite state).
- [ ] **M6 — Real orchestrator** _(orchestration)_
      Rebuild the orchestrator in LangGraph; parallel fan-out for mixed
      questions; the Hard Safety Gate becomes a dedicated graph node that
      every specialist's output must pass through (not just the safety
      specialist's own answers); resolved escalations generate a formatted
      PDF incident report as a downstream artifact of the human decision,
      never before it. The M0 hardcoded keyword net in `orchestrator.py`
      is **kept**, not deleted — it runs in parallel with the LLM router as
      a deterministic fallback (see docs/architecture.md, "why the router
      needs a net a model can't reason around").
- [ ] **M7 — Formalize the harness** _(harness, capstone)_
      Extract M3's ad hoc rules into a declarative policy config; add a
      trace replay/fork debugger; wire a CI gate that fails the build if
      escalation recall regresses.

Currently on: **M5 complete → building M6.**
