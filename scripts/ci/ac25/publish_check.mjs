// §9 C3 · §5 R6-2 — Check Run 발행 모듈(생산 판정 포함).
//
// ★workflow inline JavaScript 를 문자열로 검색해 통과시키지 않는다. 실행 가능한
//   node:test 시험이 이 모듈을 실제로 부른다.
// ★production 호출은 github.rest.checks.create 다. 다른 client 이름으로
//   계약을 쓰면 mock 은 통과하고 실물은 안 불린다.
// ★R6-2 — 기대 좌표를 이 파일에 다시 쓰지 않는다. stage_b_coordinates 단일
//   원본에서 import 한다. 40자 형식 일치만으로 통과시키지 않고 다섯 좌표와
//   합성 병합 부모 ★순서★ 까지 정확히 비교한다.
// ★발행 대상은 잠긴 후보 head 하나다. workflow input 이나 실패한 lane output 이
//   임의의 head SHA 로 대상을 바꾸지 못한다.
// ★API 오류는 짧은 code 로만 바꾼다. JavaScript stack 을 공개하지 않는다.
// ★전체 OID 를 로그에 반복하지 않는다. 짧은 8자 표시와 digest 만 남긴다(§5-2).

import {
  CoordinateContractError,
  STAGE_B_COORDINATE_CONTRACT_INVALID,
  coordinateSourceSha256,
  evaluateObserved,
  loadCoordinates,
  shortOid,
} from './stage_b_coordinates.mjs';

export const CHECK_NAME = 'box5-ac25/trusted-exact-head';
export const EXPECTED_OWNER = 'tristan00037-tristan050';
export const EXPECTED_REPO = 'tristan050-ai_ondevice_APP';

const SHA256 = /^[0-9a-f]{64}$/;
const SHORT_CODE = /^[A-Z][A-Z0-9_]{1,63}$/;

export class PublicationError extends Error {
  constructor(code) {
    super(code);
    this.name = 'PublicationError';
    this.code = code;
  }
}

// 잠긴 후보 head 는 단일 원본에서 온다. 이 파일이 값을 갖고 있지 않다.
export function lockedCandidateHead() {
  return loadCoordinates().candidate_commit;
}

export function lockedIntegrationBase() {
  return loadCoordinates().integration_base;
}

function readEnv(evidence, key) {
  const value = evidence?.[key];
  return typeof value === 'string' ? value : '';
}

// 발행 전에 대상이 신뢰할 수 있는지부터 본다. 아니면 create 를 부르지 않는다.
function assertTrustedTarget({ owner, repo, evidence, expected }) {
  if (owner !== EXPECTED_OWNER || repo !== EXPECTED_REPO) {
    throw new PublicationError('PUBLICATION_TARGET_UNTRUSTED');
  }
  const requested = readEnv(evidence, 'AC25_REQUESTED_HEAD');
  if (requested && requested !== expected.candidate_commit) {
    throw new PublicationError('PUBLICATION_TARGET_UNTRUSTED');
  }
}

// 결론과 짧은 코드를 계산한다. 하나라도 어긋나면 failure 다.
export function evaluate(evidence) {
  const reasons = [];
  const add = (code) => {
    if (!reasons.includes(code)) reasons.push(code);
  };

  let expected = null;
  try {
    expected = loadCoordinates();
  } catch (error) {
    if (!(error instanceof CoordinateContractError)) throw error;
    add(STAGE_B_COORDINATE_CONTRACT_INVALID);
  }

  for (const [key, code] of [
    ['AC25_PREFLIGHT_RESULT', 'PREFLIGHT_JOB_NOT_SUCCESS'],
    ['AC25_TRUSTED_RESULT', 'TRUSTED_JOB_NOT_SUCCESS'],
    ['AC25_CANDIDATE_RESULT', 'CANDIDATE_JOB_NOT_SUCCESS'],
    ['AC25_INTEGRATION_RESULT', 'INTEGRATION_JOB_NOT_SUCCESS'],
  ]) {
    // skipped·cancelled·neutral·빈 값은 전부 성공이 아니다(§6-5).
    if (readEnv(evidence, key) !== 'success') add(code);
  }

  // workflow 가 따로 센 관문 결과도 성공이어야 한다. 둘 중 하나만 믿지 않는다.
  if (readEnv(evidence, 'AC25_REQUIRED_JOBS_GATE') !== 'success') {
    add('REQUIRED_JOBS_NOT_ALL_SUCCESS');
  }

  if (readEnv(evidence, 'AC25_TRUSTED_VERDICT') !== '1') {
    add('TRUSTED_VERDICT_NOT_PASS');
  }

  const receiptDigest = readEnv(evidence, 'AC25_RECEIPT_SHA256');
  if (!SHA256.test(receiptDigest)) add('PUBLISH_EVIDENCE_INCOMPLETE');

  const candidateCommit = readEnv(evidence, 'AC25_CANDIDATE_COMMIT');
  const candidateTree = readEnv(evidence, 'AC25_CANDIDATE_TREE');
  const integrationBase = readEnv(evidence, 'AC25_PARENT_BASE');
  const mergeCommit = readEnv(evidence, 'AC25_MERGE_COMMIT');
  const mergeTree = readEnv(evidence, 'AC25_MERGE_TREE');
  const parentBase = readEnv(evidence, 'AC25_PARENT_BASE');
  const parentCandidate = readEnv(evidence, 'AC25_PARENT_CANDIDATE');

  // ★R6-2 생산 강제 — 다섯 좌표 + 부모 순서를 단일 원본과 정확히 비교한다.
  for (const code of evaluateObserved({
    candidateCommit,
    candidateTree,
    integrationBase,
    mergeCommit,
    mergeTree,
    mergeParents: [parentBase, parentCandidate],
    expected,
  })) {
    add(code);
  }

  const errorCode = reasons.length === 0 ? 'OK' : reasons[0];
  return {
    conclusion: reasons.length === 0 ? 'success' : 'failure',
    errorCode: SHORT_CODE.test(errorCode) || errorCode === 'OK'
      ? errorCode
      : 'PUBLISH_EVIDENCE_INCOMPLETE',
    errorCodes: Object.freeze([...reasons]),
    receiptDigest,
    candidateCommit,
    candidateTree,
    mergeCommit,
    mergeTree,
    parentBase,
    parentCandidate,
    expected,
  };
}

// summary 는 meta-only 다. 경로·원문·token·stack·전체 OID 를 넣지 않는다(§5-2).
export function buildSummary(verdict, { runUrl }) {
  let coordinateDigest = 'NONE';
  try {
    coordinateDigest = coordinateSourceSha256();
  } catch (_error) {
    coordinateDigest = 'NONE';
  }
  return [
    `verdict=${verdict.conclusion === 'success' ? 1 : 0}`,
    `error_code=${verdict.errorCode}`,
    `error_codes=${verdict.errorCodes.join(',') || 'NONE'}`,
    `coordinate_ssot_sha256=${coordinateDigest}`,
    `candidate_commit_short=${shortOid(verdict.candidateCommit)}`,
    `candidate_tree_short=${shortOid(verdict.candidateTree)}`,
    `integration_base_short=${shortOid(verdict.parentBase)}`,
    `synthetic_merge_commit_short=${shortOid(verdict.mergeCommit)}`,
    `synthetic_merge_tree_short=${shortOid(verdict.mergeTree)}`,
    `parents_short=${shortOid(verdict.parentBase)},${shortOid(verdict.parentCandidate)}`,
    `github_merge_ref_used_for_verdict=NO`,
    `receipt_sha256=${verdict.receiptDigest || 'NONE'}`,
    `run_url=${runUrl}`,
  ].join('\n');
}

export async function publishCheck({ github, owner, repo, runUrl, evidence }) {
  // 발행 대상은 좌표 단일 원본이 정한다. 계약이 깨지면 발행 자체를 하지 않는다.
  let expected;
  try {
    expected = loadCoordinates();
  } catch (error) {
    if (!(error instanceof CoordinateContractError)) throw error;
    throw new PublicationError(STAGE_B_COORDINATE_CONTRACT_INVALID);
  }

  assertTrustedTarget({ owner, repo, evidence, expected });

  const verdict = evaluate(evidence);
  const runId = readEnv(evidence, 'GITHUB_RUN_ID') || '0';

  const request = {
    owner: EXPECTED_OWNER,
    repo: EXPECTED_REPO,
    name: CHECK_NAME,
    head_sha: expected.candidate_commit,
    status: 'completed',
    conclusion: verdict.conclusion,
    external_id: `ac25:${runId}:final`,
    details_url: runUrl,
    output: {
      title: 'AC-25 trusted exact-head verification',
      summary: buildSummary(verdict, { runUrl }),
    },
  };

  try {
    // ★성공이든 실패든 정확히 한 번 발행한다. 실패라고 생략하지 않는다(M-6).
    await github.rest.checks.create(request);
  } catch (_error) {
    // ★원본 오류를 흘리지 않는다. 짧은 코드로만 바꾼다.
    throw new PublicationError('CHECK_RUN_PUBLICATION_FAILED');
  }

  if (verdict.conclusion !== 'success') {
    throw new PublicationError(verdict.errorCode);
  }
  return { conclusion: verdict.conclusion, errorCode: verdict.errorCode };
}
