# WORKSPACE FS SANDBOX POLICY — v1 (SSOT)

Date: 2026-02-15
Status: DECIDED
Scope: Agent workspace filesystem sandboxing (read/write/list)

## Goal
Workspace escape = 0 by construction.

Blocked (must be 0):
- Path traversal: ../, ..\ and any normalization that escapes root
- Absolute path: /etc, C:\, \\server\share
- Symlink escape: any symlink segment under workspace
- Write new files: creating a new file is forbidden (write-existing-only)

## Invariants (must be enforced by code)
1) User-supplied path is interpreted as relative to workspace root.
2) Any absolute path input is BLOCK.
3) Any path that normalizes to escape root is BLOCK.
4) Any path containing a symlink segment is BLOCK (fail-closed).
5) Write is allowed only to existing regular files under root; new file creation is BLOCK.
6) Must be deterministic and OS-portable.

## Implementation SSOT
- Library: scripts/agent/workspace_fs_sandbox_v1.cjs
- Self-test: scripts/agent/workspace_fs_sandbox_selftest.cjs
- Verify gate: scripts/verify/verify_workspace_fs_sandbox_v1.sh
- Repo-wide gate wiring: scripts/verify/verify_repo_contracts.sh

## DoD Keys (printed by verify only)
- WORKSPACE_FS_SANDBOX_V1_OK=1
- WORKSPACE_FS_SANDBOX_TRAVERSAL_BLOCK_OK=1
- WORKSPACE_FS_SANDBOX_ABS_BLOCK_OK=1
- WORKSPACE_FS_SANDBOX_SYMLINK_BLOCK_OK=1
- WORKSPACE_FS_SANDBOX_WRITE_NEWFILE_BLOCK_OK=1

