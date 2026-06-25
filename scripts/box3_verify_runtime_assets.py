#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from butler_pc_core.cards.box3.bundle_activation import verify_box3_bundle_activation


def main() -> int:
    report = verify_box3_bundle_activation(repo_root=REPO_ROOT)
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report.pass_ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
