# Reports

Real reports generate to `var/reports/<experiment_id>.{md,html}` at
runtime and are never committed (see `.gitignore` -- they can contain
whatever a user typed into an experiment description or lab observation).

This folder holds one **curated example** (`example_report.md` /
`example_report.html`), generated from a synthetic demo experiment with
no real lab data involved, kept here as evidence of what
`labmate.experiment.generate_report()` + `labmate.report_render.render_report_html()`
actually produce -- not just a claim in prose. Both files went through
the real code path; only the LLM synthesis call was substituted with
canned text, since no LLM backend was configured when this was generated
(see the provenance note at the top of each file for exactly what that
means for which part of the content).

## Delivery, deliberately scoped to local Markdown/HTML for now

`generate_report()` writes a local file. It does not send anything
anywhere. Sending a report externally (Google Docs, email, Slack, however)
is a genuinely separate action with its own real requirements:

- **Google Docs** specifically needs a Google Cloud project, the Docs/
  Drive API enabled, and OAuth credentials -- setup only the report's
  owner can do in their own Google account, not something this project
  can provision for them.
- Any external send is exactly the kind of action this project's own
  design principles say should require **explicit confirmation each
  time**, not an automatic step at the end of `generate_report()` --
  especially since a report may contain escalation details.

If/when external delivery gets added, it belongs as its own explicit,
separately-confirmed step layered on top of the local Markdown file this
milestone produces -- not built into report generation itself.
