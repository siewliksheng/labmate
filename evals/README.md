# Evals

## Golden set

`golden_set/` holds MIMIC-CXR reports paired with their CheXpert-labeler outputs
across 14 findings. This gives ground truth for extraction accuracy without
needing an LLM judge for the core metric.

**Do not commit MIMIC-CXR report text to this public repo** — it is
de-identified but still access-controlled under the PhysioNet data use
agreement. Commit only: report IDs, your own extraction outputs, and computed
metrics. Provide a `download_golden_set.py` script that pulls the actual
report text at eval-run time for anyone with their own credentialed access.

## Levels

| Level | What it checks | Method |
|---|---|---|
| Unit | Right tool called with right args | Assertion on tool-call trace |
| Trajectory | Efficient path, no redundant calls | Trace inspection |
| Outcome | Extracted findings match CheXpert labels | F1 vs. golden set |
| Safety | No fabricated finding without citation | Groundedness check (LLM judge + rubric, human-agreement measured) |

## Running

```bash
uv run inspect eval evals/tasks.py --model claude-sonnet-5
```

## Results

See the "Results" table in the top-level README. Regenerate it with
`uv run python evals/report.py > evals/results.md` and keep that file checked
in so CI can diff regressions.
