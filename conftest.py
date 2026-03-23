import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

collect_ignore_glob = ["tests/legacy/*"]
