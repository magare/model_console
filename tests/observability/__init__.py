from __future__ import annotations

import sys
from pathlib import Path


SRC_ROOT = Path(__file__).resolve().parents[2] / "src"

if SRC_ROOT.exists():
    src_path = str(SRC_ROOT)
    if src_path not in sys.path:
        sys.path.insert(0, src_path)
