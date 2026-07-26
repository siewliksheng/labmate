# Lab memory

Implemented in M2. Four tiers, matching the general memory-architecture
design this project is meant to teach; the actual code lives in
`src/labmate/memory/`, not here — this file is the design record.

| Tier | Scope | Store |
|---|---|---|
| Working | this conversation turn | the model's context window |
| Episodic | this session | per-session scratch state |
| Semantic | across sessions | SQLite (`var/labmate_memory.db`) — past Q&A, past image analyses + human-confirmed labels |
| Procedural | learned lab-specific behavior | the hand-authored SOP handbook (`data/sop_handbook/*.md`); HITL-distilled patterns are M4 |

## Design questions this file originally left open — now answered

- **What earns a memory?** Everything. Every completed exchange
  (`record_qa`) and every image analysis (`record_image_analysis`) is
  written automatically, unconditionally. The model is never asked
  whether something is "worth remembering" — that decision is a failure
  mode waiting to happen (it can skip something important), and retrieval
  precision is handled at read time instead (ranking + `max_results`).
- **Retrieval precision.** Currently SQL `LIKE` keyword matching, not
  embeddings — see `store.py`'s module docstring for why an embeddings
  dependency isn't justified yet. This is a real limitation: it can miss
  paraphrases and (per `sop_handbook.py`) can surface a low-relevance
  match on a common word. Known, not hidden; revisit if it causes an
  actual bad decision, not preemptively.
- **Conflict resolution.** Not yet handled for image analyses — a sample
  re-imaged later with a different result is just a second row; nothing
  currently reasons about the trend between them. This is a real gap to
  close, most likely in M4 when human-confirmed labels start attaching to
  these records and a trend actually matters for triage.
- **Decay.** Q&A and image-analysis history never expire — only
  environmental state does, by design, because it represents "is this
  still true right now," which Q&A history and past labels don't. See
  `get_environmental_state`: an expired or never-logged entry returns
  `found: false`, never the stale last-known value.

Retrieval is just-in-time everywhere (the agent calls a search tool; see
each specialist's `TOOL_SCHEMAS` in `src/labmate/specialists/`) — nothing
is pre-loaded wholesale into context. See `docs/architecture.md`.
