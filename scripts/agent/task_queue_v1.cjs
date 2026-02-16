#!/usr/bin/env node
/* eslint-disable no-console */
"use strict";

const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

function err(msg, code) {
  const e = new Error(String(msg));
  e.code = code || "BLOCK";
  return e;
}

function hashTaskId(taskId) {
  if (!taskId || typeof taskId !== "string") {
    throw err("BLOCK: task_id required", "TASK_ID");
  }
  return crypto.createHash("sha256").update(taskId).digest("hex");
}

function getTaskStatePath(stateDir, taskId) {
  const hash = hashTaskId(taskId);
  return path.join(stateDir, `${hash}.json`);
}

function readTaskState(statePath) {
  if (!fs.existsSync(statePath)) {
    return null;
  }
  try {
    const content = fs.readFileSync(statePath, "utf-8");
    return JSON.parse(content);
  } catch (e) {
    throw err(`BLOCK: task state corrupt: ${e.message}`, "STATE_CORRUPT");
  }
}

function writeTaskState(statePath, state) {
  // Atomic write: write to temp file, then rename
  const tempPath = `${statePath}.tmp.${Date.now()}.${Math.random().toString(36).substr(2, 9)}`;
  try {
    const content = JSON.stringify(state, null, 2);
    fs.writeFileSync(tempPath, content, "utf-8");
    fs.renameSync(tempPath, statePath);
  } catch (e) {
    // Cleanup temp file on error
    try {
      fs.unlinkSync(tempPath);
    } catch (_) {}
    throw err(`BLOCK: task state write failed: ${e.message}`, "WRITE_FAILED");
  }
}

function acquireLock(lockPath, timeoutMs = 10 * 60 * 1000) { // 10분 기본
  const start = Date.now();
  const pollInterval = 100; // 100ms polling interval
  while (Date.now() - start < timeoutMs) {
    try {
      // Try to create lock file exclusively
      const fd = fs.openSync(lockPath, "wx");
      fs.closeSync(fd);
      return true;
    } catch (e) {
      if (e.code === "EEXIST") {
        // Lock exists, wait and retry
        const waitMs = Math.min(pollInterval, timeoutMs - (Date.now() - start));
        if (waitMs > 0) {
          // Busy-wait (short interval)
          const end = Date.now() + waitMs;
          while (Date.now() < end) {
            // Busy-wait
          }
        }
        continue;
      }
      throw err(`BLOCK: lock acquisition failed: ${e.message}`, "LOCK_FAILED");
    }
  }
  throw err("BLOCK: lock timeout", "LOCK_TIMEOUT");
}

function releaseLock(lockPath) {
  try {
    if (fs.existsSync(lockPath)) {
      fs.unlinkSync(lockPath);
    }
  } catch (e) {
    // Best effort cleanup
  }
}

async function executeTaskV1(input) {
  const {
    task_id,
    task_fn,
    state_dir,
    max_retries = 3,
    lock_timeout_ms,
  } = input || {};

  if (!task_id || typeof task_id !== "string") {
    throw err("BLOCK: task_id required", "TASK_ID");
  }
  if (typeof task_fn !== "function") {
    throw err("BLOCK: task_fn must be a function", "TASK_FN");
  }
  if (!state_dir || typeof state_dir !== "string") {
    throw err("BLOCK: state_dir required", "STATE_DIR");
  }

  // Ensure state directory exists
  if (!fs.existsSync(state_dir)) {
    fs.mkdirSync(state_dir, { recursive: true });
  }

  const statePath = getTaskStatePath(state_dir, task_id);
  const lockPath = `${statePath}.lock`;

  // Concurrency: try to acquire lock, but check state periodically while waiting
  const lockTimeout = lock_timeout_ms ?? 10 * 60 * 1000; // 10분 기본
  const startTime = Date.now();
  const pollInterval = 100; // 100ms polling interval
  
  let lockAcquired = false;
  while (Date.now() - startTime < lockTimeout) {
    // Check if task is already completed (before acquiring lock)
    const existingState = readTaskState(statePath);
    if (existingState && existingState.status === "completed") {
      // Idempotency: return existing result without lock
      return {
        task_id,
        status: "completed",
        result: existingState.result,
        idempotent: true,
      };
    }

    // Try to acquire lock
    try {
      const fd = fs.openSync(lockPath, "wx");
      fs.closeSync(fd);
      lockAcquired = true;
      break;
    } catch (e) {
      if (e.code === "EEXIST") {
        // Lock exists, wait a bit and check state again
        const waitMs = pollInterval;
        const end = Date.now() + waitMs;
        while (Date.now() < end) {
          // Busy-wait
        }
        continue;
      }
      throw err(`BLOCK: lock acquisition failed: ${e.message}`, "LOCK_FAILED");
    }
  }

  if (!lockAcquired) {
    // Final check: maybe task completed while we were waiting
    const finalState = readTaskState(statePath);
    if (finalState && finalState.status === "completed") {
      return {
        task_id,
        status: "completed",
        result: finalState.result,
        idempotent: true,
      };
    }
    throw err("BLOCK: lock timeout", "LOCK_TIMEOUT");
  }

  try {
    // Re-check state after acquiring lock (double-check)
    const existingState = readTaskState(statePath);

    if (existingState && existingState.status === "completed") {
      // Idempotency: return existing result
      releaseLock(lockPath);
      return {
        task_id,
        status: "completed",
        result: existingState.result,
        idempotent: true,
      };
    }

    // Execute task (support async task_fn)
    let result;
    let attempts = 0;
    let lastError = null;

    while (attempts < max_retries) {
      try {
        const maybePromise = task_fn();
        result = await Promise.resolve(maybePromise);
        break;
      } catch (e) {
        lastError = e;
        attempts++;
        if (attempts >= max_retries) {
          throw e;
        }
      }
    }

    // Atomic write: write state atomically
    const newState = {
      task_id,
      status: "completed",
      result,
      completed_at_utc: new Date().toISOString(),
    };

    writeTaskState(statePath, newState);

    releaseLock(lockPath);

    return {
      task_id,
      status: "completed",
      result,
      idempotent: false,
    };
  } catch (e) {
    releaseLock(lockPath);
    throw e;
  }
}

module.exports = {
  executeTaskV1,
  hashTaskId,
  getTaskStatePath,
  readTaskState,
  writeTaskState,
  acquireLock,
  releaseLock,
};

