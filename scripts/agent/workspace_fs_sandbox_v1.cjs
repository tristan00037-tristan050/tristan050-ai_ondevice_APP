#!/usr/bin/env node
/* eslint-disable no-console */
"use strict";

const fs = require("fs");
const path = require("path");

function err(msg, code) {
  const e = new Error(String(msg));
  e.code = code || "BLOCK";
  return e;
}

function isAbsLike(p) {
  const s = String(p);

  // NUL
  if (s.includes("\0")) return true;

  // POSIX absolute
  if (s.startsWith("/")) return true;

  // Windows/UNC absolute-like even on POSIX runners
  // - C:\..., C:/...
  if (/^[a-zA-Z]:[\\/]/.test(s)) return true;
  // - \\server\share or //server/share
  if (/^[\\/]{2}/.test(s)) return true;
  // - leading backslash (e.g., \Windows\System32)
  if (s.startsWith("\\")) return true;

  // path.isAbsolute covers current platform only; keep as extra belt.
  if (path.isAbsolute(s)) return true;
  // win32 absolute check on any platform
  try {
    if (path.win32.isAbsolute(s)) return true;
  } catch (_) {}

  return false;
}

function normalizeRel(p) {
  const raw = String(p);

  // unify separators for deterministic normalize
  const unified = raw.replace(/\\/g, "/");
  let norm = path.posix.normalize(unified);

  // strip leading "./"
  norm = norm.replace(/^(\.\/)+/g, "");
  return norm;
}

function resolveUnderRoot(rootDir, relNorm) {
  const rootReal = fs.realpathSync(rootDir);
  const abs = path.resolve(rootReal, relNorm);

  const rel = path.relative(rootReal, abs);

  // If abs is outside root => rel starts with .. or is absolute (defensive)
  if (rel === "" || rel === ".") {
    return { rootReal, abs, rel: "" };
  }
  if (rel.startsWith("..") || path.isAbsolute(rel)) {
    throw err("BLOCK: path escapes workspace root", "ESCAPE");
  }
  return { rootReal, abs, rel };
}

function assertNoSymlinkSegments(rootReal, abs, allowMissingTail) {
  const rel = path.relative(rootReal, abs);
  const parts = rel.split(path.sep).filter(Boolean);

  let cur = rootReal;
  for (let i = 0; i < parts.length; i++) {
    cur = path.join(cur, parts[i]);

    if (!fs.existsSync(cur)) {
      if (allowMissingTail) return;
      throw err("BLOCK: missing path segment", "MISSING");
    }

    const st = fs.lstatSync(cur);
    if (st.isSymbolicLink()) {
      throw err("BLOCK: symlink segment detected", "SYMLINK");
    }
  }
}

function guardPathV1(rootDir, userPath, opts) {
  const mode = (opts && opts.mode) || "read"; // read | write_existing
  const s = String(userPath);

  if (!rootDir || typeof rootDir !== "string") {
    throw err("BLOCK: rootDir required", "ROOT");
  }

  if (isAbsLike(s)) {
    throw err("BLOCK: absolute path input forbidden", "ABS");
  }

  const relNorm = normalizeRel(s);

  if (!relNorm || relNorm === "." || relNorm === "./") {
    throw err("BLOCK: empty path forbidden", "EMPTY");
  }

  // traversal after normalization: ../ or ..
  if (relNorm === ".." || relNorm.startsWith("../")) {
    throw err("BLOCK: traversal forbidden", "TRAVERSAL");
  }

  const { rootReal, abs } = resolveUnderRoot(rootDir, relNorm);

  if (mode === "read") {
    if (!fs.existsSync(abs)) throw err("BLOCK: read target missing", "MISSING");
    assertNoSymlinkSegments(rootReal, abs, false);
    return { rootReal, abs, relNorm, mode };
  }

  if (mode === "write_existing") {
    // forbid new file creation
    if (!fs.existsSync(abs)) throw err("BLOCK: write new file forbidden", "NEWFILE");
    assertNoSymlinkSegments(rootReal, abs, false);

    const st = fs.lstatSync(abs);
    if (!st.isFile()) throw err("BLOCK: write target must be a regular file", "NOTFILE");
    return { rootReal, abs, relNorm, mode };
  }

  throw err(`BLOCK: unknown mode=${mode}`, "MODE");
}

module.exports = {
  guardPathV1,
};

