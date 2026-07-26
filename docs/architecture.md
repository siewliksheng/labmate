# Architecture & regulatory positioning

## Agent loop

Bare Anthropic Messages API loop (`agent.py`), not a framework, to keep the
control flow legible. Tools are defined once in `mcp_server/tools.py` and
exposed two ways: directly to the loop, and via an MCP server (`server.py`)
so they're portable to Claude Code / Claude Desktop for manual testing.

## Why compute-in-tool, not reason-in-model

Lung-RADS category and Fleischner follow-up intervals are deterministic
lookups from published tables. Letting the model "reason" its way to a
category invites silent arithmetic/table errors that are hard to catch in
eval. Both are implemented as plain Python functions the model calls as
tools; the model's job is to gather the right inputs (nodule size, type,
prior comparison) and cite its source, not to compute the table itself.

## Regulatory positioning

This system is scoped as **clinical decision support that structures and
organizes information already authored by a radiologist** — it does not
interpret images and does not generate a diagnosis. Under the 21st Century
Cures Act's CDS exemption (and FDA's related guidance on Clinical Decision
Support Software), software that displays, analyzes, or organizes
information to support a healthcare decision generally falls outside the
device definition **when the basis for the recommendation is transparent
enough for the clinician to independently review it** — which is why every
extracted finding here carries a citation back to the source sentence, and
every critical-finding flag carries the guideline computation that produced
it, not just a bare assertion.

This is a design constraint, not just a compliance footnote: it's why
citations are mandatory in the output schema and why guideline computations
happen in tools instead of model reasoning.

**This is not legal advice** — if this were a real product, the
scoping above would need sign-off from actual regulatory counsel before
launch. It's documented here to show the design consideration was made
deliberately, which is the point of a portfolio artifact.
