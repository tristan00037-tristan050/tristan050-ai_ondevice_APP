/**
 * P1-PLAT-01: Trace DB Store Test Runner (CommonJS)
 * 목적: verify 스크립트에서 실행 가능한 테스트 러너 (빌드/설치 없이)
 */

const { createRequire } = require("module");
const path = require("path");
const fs = require("fs");

// TypeScript 파일을 직접 실행할 수 없으므로,
// 여기서는 구조 검증과 정적 분석만 수행
// 실제 동작 테스트는 TypeScript 컴파일 후 별도 E2E 테스트에서 수행

function testFileStructure(ROOT) {
  const schemaPath = path.join(ROOT, "packages/ops-hub/src/trace/schema/trace_event_v1.ts");
  const storePath = path.join(ROOT, "packages/ops-hub/src/trace/store/db/sqljs_store.ts");
  const routePath = path.join(ROOT, "packages/ops-hub/src/trace/http/routes/v1_trace.ts");

  if (!fs.existsSync(schemaPath)) {
    throw new Error("BLOCK: trace_event_v1.ts not found");
  }
  if (!fs.existsSync(storePath)) {
    throw new Error("BLOCK: sqljs_store.ts not found");
  }
  if (!fs.existsSync(routePath)) {
    throw new Error("BLOCK: v1_trace.ts not found");
  }

  // sql.js 사용 확인 (better-sqlite3 금지)
  // 주의: 새로 만든 sqljs_store.ts만 검사 (기존 trace_store_sql_v1.ts는 제외)
  const storeContent = fs.readFileSync(storePath, "utf8");
  
  // P1-PLAT-01 파일인지 먼저 확인 (주석에 P1-PLAT-01 포함)
  if (!storeContent.includes("P1-PLAT-01")) {
    throw new Error("BLOCK: P1-PLAT-01 파일이 아님 (sqljs_store.ts 확인 필요)");
  }
  
  // better-sqlite3 import/require 사용 금지 확인 (주석 제외)
  // import나 require 문에서 better-sqlite3 사용 확인
  const importLines = storeContent.split('\n').filter(line => 
    line.includes('import') || line.includes('require')
  );
  const hasBetterSqlite3Import = importLines.some(line => 
    line.includes('better-sqlite3') && !line.trim().startsWith('//') && !line.trim().startsWith('*')
  );
  if (hasBetterSqlite3Import) {
    throw new Error("BLOCK: better-sqlite3 사용 금지 (sql.js 사용 필수)");
  }
  
  // sql.js 사용 확인
  if (!storeContent.includes("sql.js") && !storeContent.includes("sqljs") && !storeContent.includes("initSqlJs")) {
    throw new Error("BLOCK: sql.js 사용 확인 실패");
  }

  // PRIMARY KEY 확인 (멱등 보장)
  if (!storeContent.includes("PRIMARY KEY") && !storeContent.includes("UNIQUE")) {
    throw new Error("BLOCK: PRIMARY KEY 또는 UNIQUE 제약조건 없음 (멱등 보장 필수)");
  }

  // request_id 인덱스 확인
  if (!storeContent.includes("idx_trace_events_request_id") && !storeContent.includes("CREATE INDEX")) {
    throw new Error("BLOCK: request_id 인덱스 없음");
  }

  // INSERT OR IGNORE 또는 ON CONFLICT 확인 (멱등 보장)
  if (!storeContent.includes("INSERT OR IGNORE") && !storeContent.includes("ON CONFLICT")) {
    throw new Error("BLOCK: INSERT OR IGNORE 또는 ON CONFLICT 없음 (멱등 보장 필수)");
  }

  // validateTraceEventV1 호출 확인 (저장 전 검증)
  if (!storeContent.includes("validateTraceEventV1")) {
    throw new Error("BLOCK: validateTraceEventV1 호출 없음 (저장 전 검증 필수)");
  }

  // v1_trace.ts 검증: 로컬-only 또는 인증 확인
  const routeContent = fs.readFileSync(routePath, "utf8");
  if (!routeContent.includes("checkAccess") && !routeContent.includes("127.0.0.1") && !routeContent.includes("x-api-key")) {
    throw new Error("BLOCK: 접근 잠금 로직 없음 (로컬-only 또는 인증 필수)");
  }

  // X-Api-Key 값 매칭 확인 (존재만 금지)
  if (routeContent.includes('req.headers["x-api-key"]') || routeContent.includes("req.headers['x-api-key']")) {
    const apiKeyCheck = routeContent.match(/apiKey\s*===/);
    if (!apiKeyCheck) {
      throw new Error("BLOCK: X-Api-Key 값 매칭 없음 (존재만 확인 금지)");
    }
  }

  // trace_event_v1.ts 검증: 금지 키 검증 확인
  const schemaContent = fs.readFileSync(schemaPath, "utf8");
  if (!schemaContent.includes("validateMetaOnlyOrThrow")) {
    throw new Error("BLOCK: validateMetaOnlyOrThrow 호출 없음 (금지 키 검증 필수)");
  }

  // v1_trace.ts 검증: error_code에 e.message 사용 금지 확인
  if (routeContent.includes("error_code: e?.message") || routeContent.includes("error_code: e.message") || routeContent.includes('error_code: e?.message')) {
    throw new Error("BLOCK: error_code에 e.message 사용 금지 (짧은 코드만 사용)");
  }

  // v1_trace.ts 검증: ERROR 상수 정의 확인
  if (!routeContent.includes("const ERROR") && !routeContent.includes("ERROR =")) {
    throw new Error("BLOCK: ERROR 상수 정의 없음 (에러 코드 상수화 필수)");
  }

  // sqljs_store.ts 검증: validate 호출이 try 안에 있는지 확인
  const storeLines = storeContent.split("\n");
  let validateInTry = false;
  let inTryBlock = false;
  for (let i = 0; i < storeLines.length; i++) {
    const line = storeLines[i];
    if (line.includes("try {") || line.includes("try{")) {
      inTryBlock = true;
    }
    if (inTryBlock && line.includes("validateTraceEventV1")) {
      validateInTry = true;
      break;
    }
    if (line.includes("} catch")) {
      inTryBlock = false;
    }
  }
  if (!validateInTry) {
    throw new Error("BLOCK: validateTraceEventV1 호출이 try 블록 밖에 있음 (반드시 try 안에 있어야 함)");
  }

  // trace_event_v1.ts 검증: 사용자 값 포함 메시지 금지 확인
  if (schemaContent.includes("got '") || schemaContent.includes('got "') || schemaContent.includes("contains '") || schemaContent.includes('contains "')) {
    throw new Error("BLOCK: 에러 메시지에 사용자 값 포함 금지 (상수 메시지만 사용)");
  }

  // v1_trace.ts 검증: 기본 API 키 하드코딩 금지 확인
  if (routeContent.includes('"test-key-change-in-prod"') || routeContent.includes("'test-key-change-in-prod'")) {
    throw new Error("BLOCK: 기본 API 키 하드코딩 금지 (env 없으면 빈 문자열, fail-closed)");
  }

  // v1_trace.ts 검증: env 없을 때 fail-closed 확인
  if (!routeContent.includes("TRACE_API_KEY ?? \"\"") && !routeContent.includes("TRACE_API_KEY || \"\"")) {
    throw new Error("BLOCK: TRACE_API_KEY env 없을 때 기본값 설정 확인 필요 (빈 문자열로 fail-closed)");
  }

  return true;
}

const ROOT = process.argv[2];
if (!ROOT) {
  console.error("Usage: node test_runner.cjs <ROOT>");
  process.exit(1);
}

try {
  testFileStructure(ROOT);
  console.log("OK: 파일 구조 검증 통과");
  process.exit(0);
} catch (e) {
  console.error(e.message);
  process.exit(1);
}

