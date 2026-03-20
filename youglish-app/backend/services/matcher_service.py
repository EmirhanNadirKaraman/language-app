"""
Thin async wrapper around phrase_finder.extract_german_logic.

phrase_finder.py lives in subtitle-scraper/ and loads both the spaCy model
and the verb dictionary at module-import time (module-level globals). This
file ensures those one-time loads happen safely by:
  1. Temporarily changing CWD to the project root so the relative path
     "data/final_result.txt" inside phrase_finder resolves correctly.
  2. Adding subtitle-scraper/ to sys.path for the import.
  3. Restoring both after the import completes.

After that, `_pf` is a normal module reference; the model and dictionary
stay resident for the lifetime of the process.
"""
import asyncio
import os
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_SCRAPER_PATH = str(_PROJECT_ROOT / "subtitle-scraper")

_orig_cwd = os.getcwd()
os.chdir(_PROJECT_ROOT)
sys.path.insert(0, _SCRAPER_PATH)
try:
    import phrase_finder as _pf
finally:
    os.chdir(_orig_cwd)
    try:
        sys.path.remove(_SCRAPER_PATH)
    except ValueError:
        pass


async def match_sentence(sentence: str) -> list[dict]:
    """Run extract_german_logic in a thread so the sync spaCy call
    doesn't block the event loop."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _pf.extract_german_logic, sentence)
