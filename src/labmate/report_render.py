"""Renders a Report's Markdown synthesis into a styled, theme-aware HTML
page. Generic Markdown -> HTML via python-markdown (tables extension),
wrapped in a shared visual template -- deliberately NOT trying to parse
the model's output into bespoke structured widgets (status chips per
checklist row, etc.), since that would be fragile against whatever exact
wording the model happens to produce.

Blockquotes get a distinct "advisory" callout treatment because
experiment.REPORT_SYSTEM_PROMPT asks for Suggested Next Steps to be
written as one -- a much more robust contract than expecting an exact
heading string to key off of.
"""

import html as _html

import markdown as _markdown

_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root {{
    --paper: #f2f5f5; --paper-raised: #ffffff; --ink: #16211f; --ink-soft: #4b5b58;
    --rule: #d3dcda; --accent: #2f6f6b; --accent-soft: #e4eeed;
    --warn: #a6741a; --warn-soft: #faf0dd;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --paper: #12191a; --paper-raised: #182121; --ink: #e7efee; --ink-soft: #a9bbb8;
      --rule: #2a3735; --accent: #7cc2bb; --accent-soft: #1c2b2a;
      --warn: #e0b45c; --warn-soft: #2c2413;
    }}
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; background: var(--paper); color: var(--ink);
    font-family: -apple-system, "Segoe UI", "Helvetica Neue", Arial, sans-serif;
    font-size: 16px; line-height: 1.65; padding: 3rem 1.25rem 5rem;
  }}
  .sheet {{
    max-width: 720px; margin: 0 auto; background: var(--paper-raised);
    border: 1px solid var(--rule); border-radius: 3px; padding: 2.5rem 3rem 3rem;
  }}
  @media (max-width: 600px) {{ .sheet {{ padding: 2rem 1.25rem; }} }}
  .eyebrow {{
    font-family: Georgia, "Iowan Old Style", "Palatino Linotype", serif;
    font-size: 0.78rem; letter-spacing: 0.14em; text-transform: uppercase;
    color: var(--accent); margin: 0 0 0.6rem;
  }}
  .meta-row {{
    display: flex; flex-wrap: wrap; gap: 0.5rem 1.5rem; padding-bottom: 1.3rem;
    margin-bottom: 1.8rem; border-bottom: 1px solid var(--rule);
    font-size: 0.86rem; color: var(--ink-soft);
  }}
  .meta-row b {{ color: var(--ink); }}
  .sheet h1 {{
    font-family: Georgia, "Iowan Old Style", "Palatino Linotype", serif;
    font-weight: 600; font-size: 1.6rem; line-height: 1.3; text-wrap: balance;
    margin: 0 0 1.1rem;
  }}
  .sheet h2 {{
    font-family: Georgia, "Iowan Old Style", "Palatino Linotype", serif;
    font-size: 0.82rem; letter-spacing: 0.1em; text-transform: uppercase;
    font-weight: 600; color: var(--ink-soft); margin: 2rem 0 0.9rem;
    display: flex; align-items: center; gap: 0.6rem;
  }}
  .sheet h2::after {{ content: ""; flex: 1; height: 1px; background: var(--rule); }}
  .sheet h2:first-of-type {{ margin-top: 0; }}
  .sheet p {{ margin: 0 0 0.9rem; }}
  .sheet ul, .sheet ol {{ padding-left: 1.3rem; margin: 0 0 0.9rem; }}
  .sheet li {{ margin-bottom: 0.4rem; }}
  .table-wrap {{ overflow-x: auto; border: 1px solid var(--rule); border-radius: 3px; margin-bottom: 1rem; }}
  .sheet table {{ width: 100%; border-collapse: collapse; font-size: 0.9rem; }}
  .sheet th, .sheet td {{ text-align: left; padding: 0.65rem 0.8rem; vertical-align: top; }}
  .sheet thead th {{
    font-size: 0.72rem; letter-spacing: 0.06em; text-transform: uppercase;
    color: var(--ink-soft); background: var(--accent-soft); font-weight: 600;
  }}
  .sheet tbody tr + tr td {{ border-top: 1px solid var(--rule); }}
  .sheet blockquote {{
    background: var(--accent-soft); border-left: 3px solid var(--accent);
    border-radius: 0 3px 3px 0; margin: 0 0 1rem; padding: 0.9rem 1.1rem;
  }}
  .sheet blockquote p:last-child {{ margin-bottom: 0; }}
  .sheet strong {{ color: var(--ink); }}
  .sheet code {{
    font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
    font-variant-numeric: tabular-nums; background: var(--accent-soft);
    padding: 0.1em 0.35em; border-radius: 3px; font-size: 0.9em;
  }}
</style>
</head>
<body>
<div class="sheet">
  <p class="eyebrow">LabMate &mdash; Experiment Report</p>
  <div class="meta-row">
    <span><b>Status:</b> {status}</span>
    <span><b>Signed off by:</b> {signed_off_by}</span>
    <span><b>Experiment ID:</b> <code>{experiment_id}</code></span>
  </div>
  {body}
</div>
</body>
</html>
"""


def render_report_html(report_markdown: str, experiment: dict) -> str:
    body_html = _markdown.markdown(report_markdown, extensions=["tables"])
    description = experiment.get("description", "")
    title = (description[:70] + "...") if len(description) > 70 else description

    return _TEMPLATE.format(
        title=_html.escape(title) or "LabMate Report",
        status=_html.escape(experiment.get("status", "unknown")),
        signed_off_by=_html.escape(experiment.get("signed_off_by") or "(not yet signed off)"),
        experiment_id=_html.escape(experiment.get("id", "")),
        body=body_html,
    )
