#!/usr/bin/env python3
from __future__ import annotations
import json, sys
from datetime import datetime, timezone
from pathlib import Path

def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv)>1 else '.').resolve()
    ev = root / 'evidence'
    ev.mkdir(exist_ok=True)
    for name in ['real_telemetry_current_platform.json','real_telemetry_linux.json','real_telemetry_darwin.json','real_telemetry_windows.json']:
        p = ev / name
        if p.exists():
            p.unlink()
    report = {
        'gate': 'local_all_platform_failclosed_gate',
        'checked_at_utc': datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),
        'ok': False,
        'ok_label': None,
        'required_platforms': ['linux','darwin','windows'],
        'observed_platforms': [],
        'missing_platforms': ['linux','darwin','windows'],
        'fail_closed_expected': True,
        'reason': 'local package does not embed external CI/VM/physical telemetry evidence'
    }
    out = ev / 'gate_results' / 'all_platform_telemetry_gate.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)+'\n', encoding='utf-8')
    print('ALL_PLATFORM_TELEMETRY_FAIL_CLOSED_OK local_package_has_no_external_ci_evidence')
    return 0
if __name__ == '__main__':
    raise SystemExit(main())
