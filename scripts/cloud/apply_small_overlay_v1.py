#!/usr/bin/env python3
"""Apply AI-20/Qwen3-4B overlay changes to a local repository.

Features
- --dry-run: show unified diffs only, do not modify files and do not create backups.
- default apply mode: writes files and creates <file>.bak backups.
- --rollback: restore from <file>.bak backups.
- writes dry-run/apply metadata to tmp/ai20_overlay_dryrun_result.json.
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

REPLACEMENTS = [
    ('Qwen/Qwen2.5-7B-Instruct', 'Qwen/Qwen3-4B'),
    ('Qwen/Qwen2.5-1.5B-Instruct', 'Qwen/Qwen3-4B'),
    ('butler_model_v1', 'butler_model_small_v1'),
    ('butler_model_micro_v1', 'butler_model_small_v1'),
]

QWEN3_ADDITIONS = {
    'enable_thinking': False,
    'chat_template': 'qwen3_nonthinking',
}

TEXT_SUFFIXES = {
    '.py', '.sh', '.md', '.txt', '.json', '.jsonl', '.yaml', '.yml', '.toml', '.ini', '.cfg',
}
SKIP_DIRS = {
    '.git', '.venv', 'venv', '__pycache__', 'node_modules', 'output', 'dist', 'build', 'tmp',
}
SKIP_RELATIVE_FILES = {
    Path('scripts/cloud/apply_small_overlay_v1.py'),
}
RESULT_FILE = Path('tmp/ai20_overlay_dryrun_result.json')


@dataclass
class FileChange:
    path: str
    changed: bool
    backup_path: str | None
    diff: str
    replacements_applied: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo-dir', required=True)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--rollback', action='store_true')
    return parser.parse_args()


def is_text_file(path: Path) -> bool:
    if path.suffix.lower() in TEXT_SUFFIXES:
        return True
    try:
        data = path.read_bytes()[:1024]
    except OSError:
        return False
    if b'\x00' in data:
        return False
    return True


def iter_candidate_files(repo_dir: Path) -> Iterable[Path]:
    for path in sorted(repo_dir.rglob('*')):
        if not path.is_file():
            continue
        rel = path.relative_to(repo_dir)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if rel in SKIP_RELATIVE_FILES:
            continue
        if path.name.endswith('.bak'):
            continue
        if is_text_file(path):
            yield path


def apply_qwen3_specific_overlays(path: Path, text: str) -> tuple[str, int]:
    updates = 0
    original = text

    if path.name == 'finetune_qlora_small_v1.py':
        new_text = re.sub(
            r"('enable_thinking'\s*:\s*)(True|False)",
            r"\1False",
            text,
        )
        if new_text != text:
            text = new_text
            updates += 1
        new_text = re.sub(
            r"('chat_template'\s*:\s*)'[^']+'",
            r"\1'qwen3_nonthinking'",
            text,
        )
        if new_text != text:
            text = new_text
            updates += 1

    if original == text and "QWEN3_SPECIFIC = {" in text:
        # Verify-only case; no update counted.
        pass
    return text, updates


def diff_text(path: Path, before: str, after: str) -> str:
    if before == after:
        return ''
    return ''.join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=str(path),
            tofile=str(path),
        )
    )


def apply_overlays(repo_dir: Path, dry_run: bool) -> list[FileChange]:
    changes: list[FileChange] = []
    for path in iter_candidate_files(repo_dir):
        before = path.read_text(encoding='utf-8')
        after = before
        applied = 0
        for old, new in REPLACEMENTS:
            count = after.count(old)
            if count:
                after = after.replace(old, new)
                applied += count
        after, qwen3_updates = apply_qwen3_specific_overlays(path, after)
        applied += qwen3_updates
        diff = diff_text(path, before, after)
        changed = before != after
        backup_path = None
        if changed and not dry_run:
            backup = path.with_name(path.name + '.bak')
            if not backup.exists():
                backup.write_text(before, encoding='utf-8')
            path.write_text(after, encoding='utf-8')
            backup_path = str(backup.relative_to(repo_dir))
        changes.append(
            FileChange(
                path=str(path.relative_to(repo_dir)),
                changed=changed,
                backup_path=backup_path,
                diff=diff,
                replacements_applied=applied,
            )
        )
    return changes


def rollback(repo_dir: Path) -> list[str]:
    restored: list[str] = []
    for backup in sorted(repo_dir.rglob('*.bak')):
        original = backup.with_suffix('')
        if original.suffix == '':
            # name 'foo.py.bak' becomes 'foo.py' only with manual handling
            original = backup.with_name(backup.name[:-4])
        else:
            original = backup.with_name(backup.stem)
        original.write_text(backup.read_text(encoding='utf-8'), encoding='utf-8')
        backup.unlink()
        restored.append(str(original.relative_to(repo_dir)))
    return restored


def write_result(repo_dir: Path, payload: dict) -> None:
    result_path = repo_dir / RESULT_FILE
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding='utf-8')


def main() -> int:
    args = parse_args()
    repo_dir = Path(args.repo_dir).resolve()
    if not repo_dir.exists():
        raise SystemExit(f'Repository not found: {repo_dir}')

    if args.rollback:
        restored = rollback(repo_dir)
        write_result(repo_dir, {
            'mode': 'rollback',
            'restored_files': restored,
            'restored_count': len(restored),
            'qwen3_additions': QWEN3_ADDITIONS,
        })
        print('AI20_OVERLAY_ROLLBACK_OK=1')
        return 0

    changes = apply_overlays(repo_dir, dry_run=args.dry_run)
    changed_files = [c for c in changes if c.changed]
    payload = {
        'mode': 'dry-run' if args.dry_run else 'apply',
        'repo_dir': str(repo_dir),
        'replacement_rules': REPLACEMENTS,
        'qwen3_additions': QWEN3_ADDITIONS,
        'changed_files_count': len(changed_files),
        'changed_files': [
            {
                'path': c.path,
                'backup_path': c.backup_path,
                'replacements_applied': c.replacements_applied,
            }
            for c in changed_files
        ],
    }
    write_result(repo_dir, payload)

    for change in changed_files:
        sys.stdout.write(change.diff)
    if args.dry_run:
        print('AI20_OVERLAY_DRY_OK=1')
    else:
        print('AI20_OVERLAY_APPLY_OK=1')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
