"""Loading .env here, once, on first import of any labmate submodule, is
the fix for a real gap: python-dotenv was a declared dependency from the
start but nothing ever actually called load_dotenv() -- a .env file with
ANTHROPIC_API_KEY or LLM_BACKEND=ollama in it silently did nothing, since
os.environ.get() only sees real environment variables unless something
loads the file first. Centralized here rather than in every entry point
(app.py, agent.py, experiment.py, redteam_eval.py) so it can't be missed
in a new one later.
"""

from dotenv import load_dotenv

load_dotenv()
