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
- [ ] **M3 — The safety gate** _(guardrails, permissions)_
      Groundedness checks on every specialist's output; a code-enforced
      escalation threshold (not a prompt instruction); permission tiers
      `read` / `propose` / `escalate` — no tool exists for "declare safe".
- [ ] **M4 — Eval suite + review queue** _(evals, HITL)_
      Literature groundedness, vision accuracy vs. a labeled dataset, and
      the headline metric: safety-escalation recall on red-team cases
      (target: 100%, zero false autonomous clearances). Human review queue
      feeds resolved cases back into memory + the eval set.
- [ ] **M5 — Real orchestrator** _(orchestration)_
      Rebuild the orchestrator in LangGraph; parallel fan-out for mixed
      questions; the Hard Safety Gate becomes a dedicated graph node that
      every specialist's output must pass through (not just the safety
      specialist's own answers); resolved escalations generate a formatted
      PDF incident report as a downstream artifact of the human decision,
      never before it. The M0 hardcoded keyword net in `orchestrator.py`
      is **kept**, not deleted — it runs in parallel with the LLM router as
      a deterministic fallback (see docs/architecture.md, "why the router
      needs a net a model can't reason around").
- [ ] **M6 — Formalize the harness** _(harness, capstone)_
      Extract M3's ad hoc rules into a declarative policy config; add a
      trace replay/fork debugger; wire a CI gate that fails the build if
      escalation recall regresses.

Currently on: **M2 complete → building M3.**
