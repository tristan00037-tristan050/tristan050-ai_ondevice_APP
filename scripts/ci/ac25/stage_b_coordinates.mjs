// §5 R6-2 — 단계 B 기대 좌표의 ★단일 원본★ loader (Node).
//
// ★값을 복제하지 않는다. stage_b_coordinates.v1.json 만 읽는다.
// ★parse 후 정해진 indent(2)·key 순서로 재직렬화한 bytes 가 원본과 완전히
//   같은지 비교해 중복 키·비정규 표기를 거부한다(§5-1).
// ★반환 객체는 Object.freeze 다(§10-2). 부르는 쪽이 기대값을 바꿀 수 없다.
// ★경로·env·CLI 로 기대값을 주입받지 않는다.

import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

export const STAGE_B_COORDINATE_CONTRACT_INVALID = 'STAGE_B_COORDINATE_CONTRACT_INVALID';
export const SCHEMA_VERSION = 'butler.ac25.stage_b_coordinates.v1';
export const COORDINATE_FILENAME = 'stage_b_coordinates.v1.json';

export const CANDIDATE_COMMIT_MISMATCH = 'CANDIDATE_COMMIT_MISMATCH';
export const CANDIDATE_TREE_MISMATCH = 'CANDIDATE_TREE_MISMATCH';
export const INTEGRATION_BASE_MISMATCH = 'INTEGRATION_BASE_MISMATCH';
export const MERGE_COMMIT_MISMATCH = 'MERGE_COMMIT_MISMATCH';
export const MERGE_TREE_MISMATCH = 'MERGE_TREE_MISMATCH';
export const MERGE_PARENT_COUNT_MISMATCH = 'MERGE_PARENT_COUNT_MISMATCH';
export const MERGE_PARENT_ORDER_MISMATCH = 'MERGE_PARENT_ORDER_MISMATCH';

// ★§5-2 가 정한 보고 순서.
export const FAILURE_ORDER = Object.freeze([
  STAGE_B_COORDINATE_CONTRACT_INVALID,
  CANDIDATE_COMMIT_MISMATCH,
  CANDIDATE_TREE_MISMATCH,
  INTEGRATION_BASE_MISMATCH,
  MERGE_COMMIT_MISMATCH,
  MERGE_TREE_MISMATCH,
  MERGE_PARENT_COUNT_MISMATCH,
  MERGE_PARENT_ORDER_MISMATCH,
]);

const KEY_ORDER = Object.freeze([
  'schema_version',
  'candidate_commit',
  'candidate_tree',
  'integration_base',
  'merge_commit',
  'merge_tree',
]);
const OID_KEYS = Object.freeze(KEY_ORDER.slice(1));
const OID = /^[0-9a-f]{40}$/;
const ALL_ZERO_OID = '0'.repeat(40);

export class CoordinateContractError extends Error {
  constructor(code = STAGE_B_COORDINATE_CONTRACT_INVALID) {
    super(code);
    this.name = 'CoordinateContractError';
    this.code = code;
  }
}

export function coordinatePath() {
  return join(dirname(fileURLToPath(import.meta.url)), COORDINATE_FILENAME);
}

export function canonicalBytes(mapping) {
  const ordered = {};
  for (const key of KEY_ORDER) ordered[key] = mapping[key];
  return Buffer.from(`${JSON.stringify(ordered, null, 2)}\n`, 'utf8');
}

// JSON.parse 는 중복 키를 조용히 덮어쓴다. reviver 로 직접 세어 거부한다.
function parseStrict(text) {
  let parsed;
  try {
    parsed = JSON.parse(text);
  } catch (_error) {
    throw new CoordinateContractError();
  }
  if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new CoordinateContractError();
  }
  const keys = Object.keys(parsed);
  if (keys.length !== KEY_ORDER.length) throw new CoordinateContractError();
  for (const key of KEY_ORDER) {
    if (!Object.prototype.hasOwnProperty.call(parsed, key)) {
      throw new CoordinateContractError();
    }
    if (typeof parsed[key] !== 'string') throw new CoordinateContractError();
  }
  return parsed;
}

export function loadFromBytes(raw) {
  if (!Buffer.isBuffer(raw) || raw.length === 0) throw new CoordinateContractError();
  let text;
  try {
    text = new TextDecoder('utf-8', { fatal: true }).decode(raw);
  } catch (_error) {
    throw new CoordinateContractError();
  }
  const parsed = parseStrict(text);
  if (parsed.schema_version !== SCHEMA_VERSION) throw new CoordinateContractError();
  for (const key of OID_KEYS) {
    if (!OID.test(parsed[key]) || parsed[key] === ALL_ZERO_OID) {
      throw new CoordinateContractError();
    }
  }
  // ★canonical 재직렬화 대조 — 중복 키·공백 장난은 여기서 걸린다
  if (!canonicalBytes(parsed).equals(raw)) throw new CoordinateContractError();

  const frozen = {};
  for (const key of KEY_ORDER) frozen[key] = parsed[key];
  frozen.expectedMergeParents = Object.freeze([
    parsed.integration_base,
    parsed.candidate_commit,
  ]);
  return Object.freeze(frozen);
}

export function loadCoordinates() {
  let raw;
  try {
    raw = readFileSync(coordinatePath());
  } catch (_error) {
    throw new CoordinateContractError();
  }
  return loadFromBytes(raw);
}

export function coordinateSourceSha256() {
  try {
    return createHash('sha256').update(readFileSync(coordinatePath())).digest('hex');
  } catch (_error) {
    throw new CoordinateContractError();
  }
}

// §5-2 — 관측 좌표를 기대 좌표와 정확히 비교한다. 형식 일치는 통과가 아니다.
export function evaluateObserved({
  candidateCommit,
  candidateTree,
  integrationBase,
  mergeCommit,
  mergeTree,
  mergeParents,
  expected = null,
}) {
  let expectation;
  try {
    expectation = expected ?? loadCoordinates();
  } catch (_error) {
    return Object.freeze([STAGE_B_COORDINATE_CONTRACT_INVALID]);
  }

  const codes = [];
  const check = (observed, want, code) => {
    if (typeof observed !== 'string' || !OID.test(observed) || observed !== want) {
      codes.push(code);
    }
  };

  check(candidateCommit, expectation.candidate_commit, CANDIDATE_COMMIT_MISMATCH);
  check(candidateTree, expectation.candidate_tree, CANDIDATE_TREE_MISMATCH);
  check(integrationBase, expectation.integration_base, INTEGRATION_BASE_MISMATCH);
  check(mergeCommit, expectation.merge_commit, MERGE_COMMIT_MISMATCH);
  check(mergeTree, expectation.merge_tree, MERGE_TREE_MISMATCH);

  if (!Array.isArray(mergeParents) || mergeParents.length !== 2) {
    codes.push(MERGE_PARENT_COUNT_MISMATCH);
  } else if (
    mergeParents[0] !== expectation.expectedMergeParents[0]
    || mergeParents[1] !== expectation.expectedMergeParents[1]
  ) {
    codes.push(MERGE_PARENT_ORDER_MISMATCH);
  }

  const unique = [...new Set(codes)];
  unique.sort((left, right) => FAILURE_ORDER.indexOf(left) - FAILURE_ORDER.indexOf(right));
  return Object.freeze(unique);
}

// 로그에는 전체 OID 를 반복하지 않는다(§5-2). 짧은 8자 표시만 허용한다.
export function shortOid(value) {
  return typeof value === 'string' && OID.test(value) ? value.slice(0, 8) : 'NONE';
}

export function oidDigest(value) {
  return createHash('sha256').update(String(value ?? '')).digest('hex');
}
