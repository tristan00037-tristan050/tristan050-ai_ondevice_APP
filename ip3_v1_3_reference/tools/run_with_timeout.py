#!/usr/bin/env python3
from __future__ import annotations
import argparse, subprocess, sys

def main() -> int:
    ap = argparse.ArgumentParser(description='Run a command with a timeout and forward its output.')
    ap.add_argument('--seconds', type=float, default=30.0)
    ap.add_argument('cmd', nargs=argparse.REMAINDER)
    args = ap.parse_args()
    cmd = args.cmd
    if cmd and cmd[0] == '--':
        cmd = cmd[1:]
    if not cmd:
        print('RUN_WITH_TIMEOUT_FAIL missing command', file=sys.stderr)
        return 2
    try:
        cp = subprocess.run(cmd, timeout=args.seconds)
        return cp.returncode
    except subprocess.TimeoutExpired:
        print(f'RUN_WITH_TIMEOUT_FAIL timeout_seconds={args.seconds} cmd={cmd!r}', file=sys.stderr)
        return 124
if __name__ == '__main__':
    raise SystemExit(main())
