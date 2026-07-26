# Lab memory

Landing in M2. Four tiers, matching the general memory-architecture design
this project is meant to teach:

| Tier | Scope | Store |
|---|---|---|
| Working | this conversation turn | the model's context window |
| Episodic | this session | per-session scratch state |
| Semantic | across sessions | Postgres + pgvector — past Q&A, past image analyses paired with human-confirmed labels |
| Procedural | learned lab-specific behavior | the SOP/handbook corpus, and later, patterns distilled from HITL corrections (M4) |

## Write policy (design questions to answer when this lands)

- What earns a memory? (Every image analysis? Only ones a human confirmed?)
- Retrieval precision: wrong-memory recall is worse than no memory — how is
  that measured before this ships?
- Conflict resolution: a sample re-imaged a week later with a different
  result — does the old entry get superseded, or does the agent need to
  reason about the trend?
- Decay: does anything ever get demoted or removed, and on what basis?

Retrieval must be just-in-time (the agent searches memory via a tool) —
never pre-loaded wholesale into context. See `docs/architecture.md`.
