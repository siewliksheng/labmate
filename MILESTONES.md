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
      unresolved item, is committed at `reports/example_report.md` and
      was also rendered live as an HTML Artifact. Covered by
      `tests/test_experiment.py` (6 tests, no network or API key
      required — the LLM synthesis calls are monkeypatched).
- [ ] **M5 — Eval suite + review queue** _(evals, HITL)_
      Literature groundedness, vision accuracy vs. a labeled dataset, and
      the headline metric: safety-escalation recall on red-team cases
      (target: 100%, zero false autonomous clearances). Human review queue
      feeds resolved cases back into memory + the eval set.
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

Currently on: **M4 complete → building M5.**
