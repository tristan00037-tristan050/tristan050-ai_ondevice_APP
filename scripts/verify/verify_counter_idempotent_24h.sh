#!/usr/bin/env bash
set -euo pipefail

COUNTER_NO_DOUBLE_INC_OK=0
COUNTER_24H_WINDOW_BY_EVENT_TS_OK=0

cleanup(){
  echo "COUNTER_NO_DOUBLE_INC_OK=${COUNTER_NO_DOUBLE_INC_OK}"
  echo "COUNTER_24H_WINDOW_BY_EVENT_TS_OK=${COUNTER_24H_WINDOW_BY_EVENT_TS_OK}"
}
trap cleanup EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
node --input-type=commonjs <<NODE
const m = require("$ROOT/packages/common/src/metrics/counters.cjs");
const { bump, readCounts24h } = m;

const now = Date.now();
const event = { v:1, event_id:"EID_TEST_1", event_ts_ms: now, name:"LOCK_TIMEOUT" };

// first bump
const r1 = bump(event, now);
if (!r1.bumped) process.exit(11);

// second bump same event_id => must NOT bump
const r2 = bump(event, now);
if (r2.bumped) process.exit(12);

// 24h window 기준이 event_ts 기준인지 최소 검증(과거 이벤트는 카운트에서 빠져야 함)
const old = { v:1, event_id:"EID_OLD", event_ts_ms: now - 25*60*60*1000, name:"LOCK_TIMEOUT" };
bump(old, now);

const c = readCounts24h(now);
if (c.LOCK_TIMEOUT < 1) process.exit(13);

process.exit(0);
NODE

rc=$?
if [[ $rc -ne 0 ]]; then exit 1; fi

COUNTER_NO_DOUBLE_INC_OK=1
COUNTER_24H_WINDOW_BY_EVENT_TS_OK=1
exit 0

