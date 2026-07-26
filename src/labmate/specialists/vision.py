"""Vision specialist -- identifies/describes lab sample images.

M1: the analyze_image tool now exists and performs two independent passes
-- descriptive and hazard-scan (VISION_DESCRIPTIVE_PROMPT /
VISION_HAZARD_SCAN_PROMPT below; mcp_server/tools.py imports these). Image
bytes never enter this specialist's own conversation context -- only the
tool's structured text findings do, which keeps the outer loop's context
small and keeps the vision capability isolated behind one tool boundary
(see docs/architecture.md). analyze_image also records every analysis to
memory automatically (see labmate.memory.store).

M2 adds search_past_image_analyses so a new analysis can be compared
against labeled history instead of judged in isolation -- e.g. "the last
three flasks with this discoloration pattern were confirmed contaminated"
is a materially different signal than a first-time observation, even
though this specialist still isn't the one deciding what that signal
means. The specialist still never issues a safe/unsafe verdict itself;
M3 makes "no verdict from this specialist" a code-enforced rule rather
than a prompt instruction.
"""

from labmate.mcp_server.tools import TOOL_SCHEMAS as _ALL_TOOLS

VISION_DESCRIPTIVE_PROMPT = """\
Describe what this lab sample image shows: sample type, visible \
morphology, apparent condition. Be literal and specific. You are not \
making a safety determination -- that is a separate process. Do not use \
words like "safe," "fine," "normal," or "dangerous."
"""

VISION_HAZARD_SCAN_PROMPT = """\
Examine this image specifically for anything a hazard-scan should catch \
that a description of the main subject would miss: cracked or damaged \
glassware anywhere in frame including edges and background, discoloration \
inconsistent with the labeled sample, unlabeled containers, signs of \
contamination, spills, or improper storage. List each finding separately \
with its location in the frame. If you find nothing, say so explicitly -- \
do not infer safety from the absence of findings in this pass alone; that \
inference belongs to the safety gate, not to you.
"""

SYSTEM_PROMPT = """\
A lab member wants to know what a sample image shows. Call analyze_image \
with the image path they gave you. Then call search_past_image_analyses \
with a short description of what you found, to check whether similar \
samples have been seen and labeled before -- mention any relevant match \
explicitly, including its human_label if one is set. Relay the \
descriptive findings, the hazard-scan findings, and any relevant past \
match plainly, as separate observations. Never synthesize these into a \
single safe/unsafe verdict -- say that any hazard implication needs the \
safety specialist or a human to confirm.
"""

TOOL_SCHEMAS = [t for t in _ALL_TOOLS if t["name"] in {"analyze_image", "search_past_image_analyses"}]
