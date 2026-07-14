#!/usr/bin/env bash
set -euo pipefail
umask 077

[[ $# -eq 2 ]] || { echo 'usage: package_from_git.sh <full-commit-oid> <output-dir>' >&2; exit 10; }
COMMIT="$1"
OUT="$2"
FULL="$(git rev-parse --verify "${COMMIT}^{commit}")"
FORMAT="$(git rev-parse --show-object-format)"
case "$FORMAT" in sha1) [[ "$FULL" =~ ^[0-9a-f]{40}$ ]] ;; sha256) [[ "$FULL" =~ ^[0-9a-f]{64}$ ]] ;; *) exit 11 ;; esac
test -z "$(git status --porcelain=v1 --untracked-files=all)"
mkdir -p "$OUT"
git archive --format=tar --prefix=release/ "$FULL" | gzip -n > "$OUT/release.tar.gz"
git ls-tree -r --full-tree "$FULL" > "$OUT/git-tree.txt"
git show --no-patch --format=fuller "$FULL" > "$OUT/commit.txt"
sha256sum "$OUT/release.tar.gz" "$OUT/git-tree.txt" "$OUT/commit.txt" > "$OUT/SHA256SUMS"
