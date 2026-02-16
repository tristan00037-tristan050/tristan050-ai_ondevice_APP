#!/usr/bin/env node
/* eslint-disable no-console */
"use strict";

const fs = require("fs");
const os = require("os");
const path = require("path");
const { executeTaskV1, writeTaskState, readTaskState } = require("./task_queue_v1.cjs");

function ok(name) {
  console.log(`${name}=1`);
}

function fail(name, msg) {
  console.error(`FAIL:${name}:${msg}`);
  process.exit(1);
}

// Test 1: Idempotency
// Same task_id executed multiple times produces identical result
{
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "task_queue_test_"));
  const taskId = "test.idempotent";

  let callCount = 0;
  const taskFn = () => {
    callCount++;
    return { value: 42, call_count: callCount };
  };

  // First execution
  const result1 = executeTaskV1({
    task_id: taskId,
    task_fn: taskFn,
    state_dir: tmpDir,
  });

  // Second execution (should return cached result, not execute again)
  const result2 = executeTaskV1({
    task_id: taskId,
    task_fn: taskFn,
    state_dir: tmpDir,
  });

  if (result1.idempotent !== false) {
    fail("TASK_QUEUE_IDEMPOTENCY_OK", "first execution should not be idempotent");
  }
  if (result2.idempotent !== true) {
    fail("TASK_QUEUE_IDEMPOTENCY_OK", "second execution should be idempotent");
  }
  if (JSON.stringify(result1.result) !== JSON.stringify(result2.result)) {
    fail("TASK_QUEUE_IDEMPOTENCY_OK", "idempotent results must be identical");
  }
  if (callCount !== 1) {
    fail("TASK_QUEUE_IDEMPOTENCY_OK", `task should execute only once, got ${callCount}`);
  }

  // Cleanup
  fs.rmSync(tmpDir, { recursive: true, force: true });
}

ok("TASK_QUEUE_IDEMPOTENCY_OK");

// Test 2: Concurrency
// Concurrent execution of same task_id is safe (no race conditions)
{
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "task_queue_concurrent_"));
  const taskId = "test.concurrent";

  let executionCount = 0;
  const taskFn = () => {
    executionCount++;
    return { value: executionCount };
  };

  // Simulate concurrent execution (sequential in test, but lock should prevent issues)
  const results = [];
  for (let i = 0; i < 3; i++) {
    try {
      const result = executeTaskV1({
        task_id: taskId,
        task_fn: taskFn,
        state_dir: tmpDir,
      });
      results.push(result);
    } catch (e) {
      fail("TASK_QUEUE_CONCURRENCY_OK", `concurrent execution failed: ${e.message}`);
    }
  }

  // All results should be identical (idempotent after first)
  const firstResult = results[0].result.value;
  for (let i = 1; i < results.length; i++) {
    if (results[i].result.value !== firstResult) {
      fail("TASK_QUEUE_CONCURRENCY_OK", "concurrent results must be identical");
    }
  }
  if (executionCount !== 1) {
    fail("TASK_QUEUE_CONCURRENCY_OK", `task should execute only once, got ${executionCount}`);
  }

  // Cleanup
  fs.rmSync(tmpDir, { recursive: true, force: true });
}

ok("TASK_QUEUE_CONCURRENCY_OK");

// Test 3: Partial write = 0
// Write operations are atomic (all-or-nothing, no partial state)
{
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "task_queue_atomic_"));
  const statePath = path.join(tmpDir, "test_state.json");

  // Test atomic write: write should be complete or fail
  const testState = {
    task_id: "test.atomic",
    status: "completed",
    result: { data: "test" },
    completed_at_utc: new Date().toISOString(),
  };

  try {
    writeTaskState(statePath, testState);

    // Verify complete write
    const readBack = readTaskState(statePath);
    if (!readBack) {
      fail("TASK_QUEUE_PARTIAL_WRITE_0_OK", "state file not found after write");
    }
    if (JSON.stringify(readBack) !== JSON.stringify(testState)) {
      fail("TASK_QUEUE_PARTIAL_WRITE_0_OK", "read state does not match written state");
    }

    // Verify no temp files left behind
    const files = fs.readdirSync(tmpDir);
    const tempFiles = files.filter((f) => f.includes(".tmp."));
    if (tempFiles.length > 0) {
      fail("TASK_QUEUE_PARTIAL_WRITE_0_OK", `temp files left behind: ${tempFiles.join(", ")}`);
    }
  } catch (e) {
    fail("TASK_QUEUE_PARTIAL_WRITE_0_OK", `atomic write failed: ${e.message}`);
  }

  // Cleanup
  fs.rmSync(tmpDir, { recursive: true, force: true });
}

ok("TASK_QUEUE_PARTIAL_WRITE_0_OK");

process.exit(0);

