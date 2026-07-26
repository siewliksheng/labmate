# Evals

Landing in M4, but the folder layout is fixed now so later commits are pure
additions, not restructuring.

## Three eval sets

| Set | Folder | What it measures |
|---|---|---|
| Literature groundedness | `golden_set/literature/` | Every citation in a summary resolves to an actually-retrieved abstract; no fabricated sources |
| Vision accuracy | `golden_set/vision/` | Agreement with a labeled public microscopy/contamination dataset |
| **Safety escalation recall** | `redteam_safety/` | The headline metric: on adversarial/ambiguous hazard prompts, does the agent escalate instead of answering? Target: 100% recall, 0 false autonomous clearances |

## Why escalation recall is the metric that matters most

A literature agent that hallucinates a citation is embarrassing. A safety
agent that confidently clears something as safe when it wasn't is the one
failure mode this whole project exists to prevent — so it gets measured
separately from everything else, and CI (M6) fails the build on any
regression in it specifically, not just on an aggregate score.

Escalation **precision** (on a benign-query set) is tracked alongside it —
see docs/architecture.md, "alarm fatigue" — but recall is what CI gates on.

## Running (once M4 lands)

```bash
uv run inspect eval evals/tasks.py --model claude-sonnet-5
```

## Do not commit real lab data here

Only synthetic/public data (see top-level README "Data"). The red-team
safety set in `redteam_safety/` is authored by hand, including
intentionally ambiguous edge cases — that's the point of writing it
yourself rather than sourcing it from a real lab.
