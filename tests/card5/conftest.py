"""Card 5 tests 본 sys.path 본 본 본 — butler.card5 import 가능."""
from __future__ import annotations

import sys
from pathlib import Path

# 본 src/ 본 sys.path 본 본 (본 리포 pythonpath = "." 본 본 본 본 butler import 가능)
_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
