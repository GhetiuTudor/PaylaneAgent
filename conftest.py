# conftest.py — makes the project root importable by pytest
# (no setup.py / pyproject.toml in this repo, so the root is registered manually)
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
