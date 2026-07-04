#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

REQ = [
    '_HYPHEN_CHARS', '_ACCOUNT_HYPHEN_RE', '_has_hyphenated_account',
    '_KO_SECRET_RE', '_KO_SECRET_SAFE_START', '_has_ko_secret',
    'unicodedata.normalize', '_dlp_scan_all',
]


def main() -> int:
    root = Path.cwd()
    target = root / 'butler_pc_core/connect_loop/persisted_safety.py'
    if not target.exists():
        print('DLP_GAP_PATCH_OK=0')
        print('reason=PERSISTED_SAFETY_MISSING')
        return 1
    text = target.read_text(encoding='utf-8')
    missing = [x for x in REQ if x not in text]
    if missing:
        print('DLP_GAP_PATCH_OK=0')
        for item in missing:
            print('missing=' + item)
        return 1
    print('DLP_GAP_PATCH_OK=1')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
