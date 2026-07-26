"""Shared local paths for runtime artifacts that aren't part of the repo
content itself (escalation queue, fallback trace export). Never committed
-- see .gitignore.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
VAR_DIR = REPO_ROOT / "var"
