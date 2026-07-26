# Architecture & critical assessment

## The core design: specialists never answer directly

Every specialist (literature, vision, safety) produces a *draft* response.
No draft reaches the user until it has passed the **Hard Safety Gate** — a
node that runs regardless of which specialist produced the draft, because a
hazard can hide in a literature summary or a vision description just as
easily as in an explicit safety question. This is the one design decision
everything else in this doc is in service of.

## Critical assessment of the original design (and the fixes it drove)

The initial design (router → specialists → safety agent clears hazardous
questions) has five real gaps. Each one is why the architecture below looks
the way it does, not a hypothetical concern:

**1. A single LLM safety evaluator is a single point of failure.**
If "is this safe?" is answered by one model call, nothing stops that call
from being confidently wrong — that's the exact failure mode the whole
project exists to prevent, just moved one layer down. Fix: the gate is not
one model call. It's a **deterministic check first** (hazard-keyword /
entity match against a controlled list — can't be reasoned around) **and**
an LLM groundedness evaluator second. Either one flagging a hazard is
sufficient to escalate; both must clear for a response to pass.

**2. LLM confidence scores are not a trustworthy gate signal.**
A model's self-reported confidence is not calibrated to real risk. The gate
therefore never asks "how confident is the model?" — it asks "**is every
claim in this draft backed by a retrieved source that unambiguously covers
this exact situation?**" No matching source, or a source that only
partially covers the case, means escalate. This reframes the gate from a
subjective threshold to a coverage check, which is falsifiable and testable.

**3. A fast router model can misroute a safety-relevant query away from
safety entirely** — and a query that never reaches the safety specialist
never reaches the gate either. Fix: the hardcoded keyword net from M0
(`orchestrator.py`) is **not retired when the LLM router (M5) ships**. It
runs in parallel as a deterministic fallback that can force a safety route
regardless of what the router model decided. A model can be argued with; a
substring match cannot.

**4. Absence of a match is not the same as clearance** (the
multi-agent-contradiction case: literature agent proposes a novel chemical
protocol, safety agent finds nothing in the SDS/SOP database, and treats
"not flagged" as "cleared"). Fix: the gate's coverage check treats **"no
matching entry found" as unresolved, and unresolved routes to escalation**,
never to a pass. An unknown substance is not a safe one by default.

**5. A single holistic image caption can miss a peripheral hazard**
(cracked glass at the frame edge, discoloration in the background) because
captioning models attend to the salient subject. Fix: `analyze_image` (M1)
is two passes, not one — a descriptive pass on the subject, and a separate
hazard-scan pass explicitly prompted to check edges/background/unlabeled
containers. Either pass flagging something routes to the gate as "hazard
signal present," even if the descriptive pass came back clean.

A sixth issue worth tracking even though it's not a red-team scenario:
**escalation precision isn't in the stated target.** 100% recall is the
right priority, but if the false-escalation rate is high, lab members will
route around the tool out of frustration — a real-world safety failure
mode (alarm fatigue) that a recall-only metric hides. M4's eval suite
reports escalation precision on a benign-query set alongside recall on the
red-team set, and precision is watched even though recall is what CI gates
on.

## Why safety routing wins every tie

If a query matches both a safety keyword and an image is attached, or both
a safety and literature keyword, safety wins. The cost of an unnecessary
escalation is a human spending two minutes on a benign question. The cost
of a missed one is physical harm. That asymmetry is the whole reason this
project exists, so ties resolve in the direction of the expensive-but-safe
outcome, not the average case.

## Environmental state (M2)

Static SOPs answer "is chemical X hazardous." They can't answer "is it
safe to run this centrifuge right now" if someone logged an active Bunsen
burner on the adjacent bench an hour ago. Environmental-state memory is a
separate store from the SOP corpus, keyed by bench/location, with:
- **Provenance** — who logged it, when
- **TTL** — entries expire (default 2h, configurable per hazard type)
- **Expiry reads as "unknown," never "safe"** — the gate cannot treat a
  stale entry as evidence of a currently-safe environment

## PDF incident reports (M5)

Generated **only** as a downstream artifact of a human's resolution of an
escalated case — never generated to accompany an unresolved escalation,
and never presented as a verdict in its own right. The report documents
what was asked, what the gate found, and what the human decided; it is a
record, not a second opinion.

## What is *not* in scope

This system does not attempt to autonomously classify novel hazards it has
no source for — see point 4 above. It does not replace a lab's actual
safety officer, SDS binder, or institutional biosafety review. Every
escalation path assumes a human is the actual decision-maker; the system's
job is routing the right questions to that human fast enough to be useful,
and never letting a question that should have reached them get quietly
answered instead.
