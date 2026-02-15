#!/usr/bin/env node
/* eslint-disable no-console */
"use strict";

const fs = require("fs");
const os = require("os");
const path = require("path");
const { guardPathV1 } = require("./workspace_fs_sandbox_v1.cjs");

function ok(name) {
  console.log(`${name}=1`);
}
function fail(name, msg) {
  console.error(`FAIL:${name}:${msg}`);
  process.exit(1);
}
function mustThrow(name, fn, codePrefix) {
  let threw = false;
  try {
    fn();
  } catch (e) {
    threw = true;
    if (codePrefix && !String(e.code || "").startsWith(codePrefix)) {
      // allow mismatched internal code but still must be BLOCK
      // keep deterministic: treat as failure
      fail(name, `unexpected code=${e.code}`);
    }
  }
  if (!threw) fail(name, "expected throw but succeeded");
}

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "ws_sbx_"));
const root = tmp;
const a = path.join(root, "a.txt");
fs.writeFileSync(a, "hello", "utf8");

// create symlink escape fixture
const outside = fs.mkdtempSync(path.join(os.tmpdir(), "ws_sbx_out_"));
const outsideFile = path.join(outside, "secret.txt");
fs.writeFileSync(outsideFile, "secret", "utf8");
const link = path.join(root, "lnk");
try {
  // link points outside root -> must be blocked
  fs.symlinkSync(outside, link, "dir");
} catch (e) {
  fail("WORKSPACE_FS_SANDBOX_SYMLINK_BLOCK_OK", `symlink create failed: ${e.message}`);
}

// 1) traversal
mustThrow("WORKSPACE_FS_SANDBOX_TRAVERSAL_BLOCK_OK", () => {
  guardPathV1(root, "../etc/passwd", { mode: "read" });
}, "TRAVERSAL");

// 2) absolute
mustThrow("WORKSPACE_FS_SANDBOX_ABS_BLOCK_OK", () => {
  guardPathV1(root, "/etc/passwd", { mode: "read" });
}, "ABS");

// also windows absolute-like patterns must be blocked on any OS
mustThrow("WORKSPACE_FS_SANDBOX_ABS_BLOCK_OK", () => {
  guardPathV1(root, "C:\\Windows\\System32\\drivers\\etc\\hosts", { mode: "read" });
}, "ABS");

// 3) symlink segment (symlink itself should be blocked when accessing through it)
mustThrow("WORKSPACE_FS_SANDBOX_SYMLINK_BLOCK_OK", () => {
  guardPathV1(root, "lnk/secret.txt", { mode: "read" });
}, "SYMLINK");

// 4) write new file forbidden
mustThrow("WORKSPACE_FS_SANDBOX_WRITE_NEWFILE_BLOCK_OK", () => {
  guardPathV1(root, "new.txt", { mode: "write_existing" });
}, "NEWFILE");

// 5) write existing allowed (optional but good sanity)
try {
  const r = guardPathV1(root, "a.txt", { mode: "write_existing" });
  fs.writeFileSync(r.abs, "updated", "utf8");
} catch (e) {
  fail("WORKSPACE_FS_SANDBOX_V1_OK", `write existing failed: ${e.message}`);
}

ok("WORKSPACE_FS_SANDBOX_TRAVERSAL_BLOCK_OK");
ok("WORKSPACE_FS_SANDBOX_ABS_BLOCK_OK");
ok("WORKSPACE_FS_SANDBOX_SYMLINK_BLOCK_OK");
ok("WORKSPACE_FS_SANDBOX_WRITE_NEWFILE_BLOCK_OK");
ok("WORKSPACE_FS_SANDBOX_V1_OK");
process.exit(0);

