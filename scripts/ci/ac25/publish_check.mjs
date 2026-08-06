// §9 C3 — Check Run 발행 모듈.
//
// ★workflow inline JavaScript 를 문자열로 검색해 통과시키지 않는다. 실행 가능한
//   node:test 시험이 이 모듈을 실제로 부른다.
// ★production 호출은 github.rest.checks.create 다. 다른 client 이름으로
//   계약을 쓰면 mock 은 통과하고 실물은 안 불린다.
// ★발행 대상은 잠긴 후보 head 하나다. workflow input 이나 실패한 lane output 이
//   임의의 head SHA 로 대상을 바꾸지 못한다.
// ★API 오류는 짧은 code 로만 바꾼다. JavaScript stack 을 공개하지 않는다.

export const CHECK_NAME = 'box5-ac25/trusted-exact-head';
export const LOCKED_CANDIDATE_HEAD = '61ba1bf48d4ce5aa62f256ef80fc84e4e8aafd04';
export const LOCKED_INTEGRATION_BASE = 'afdb237e4e6e83d96a182b6c5366a2ad95949bee';
export const EXPECTED_OWNER = 'tristan00037-tristan050';
export const EXPECTED_REPO = 'tristan050-ai_ondevice_APP';

const OID = /^[0-9a-f]{40}$/;
const SHA256 = /^[0-9a-f]{64}$/;
const SHORT_CODE = /^[A-Z][A-Z0-9_]{1,63}$/;

export class PublicationError extends Error {
  constructor(code) {
    super(code);
    this.name = 'PublicationError';
    this.code = code;
  }
}

function readEnv(evidence, key) {
  const value = evidence?.[key];
  return typeof value === 'string' ? value : '';
}

// 발행 전에 대상이 신뢰할 수 있는지부터 본다. 아니면 create 를 부르지 않는다.
function assertTrustedTarget({ owner, repo, evidence }) {
  if (owner !== EXPECTED_OWNER || repo !== EXPECTED_REPO) {
    throw new PublicationError('PUBLICATION_TARGET_UNTRUSTED');
  }
  const requested = readEnv(evidence, 'AC25_REQUESTED_HEAD');
  if (requested && requested !== LOCKED_CANDIDATE_HEAD) {
    throw new PublicationError('PUBLICATION_TARGET_UNTRUSTED');
  }
}

// 결론과 짧은 코드를 계산한다. 하나라도 어긋나면 failure 다.
export function evaluate(evidence) {
  const reasons = [];
  const add = (code) => {
    if (!reasons.includes(code)) reasons.push(code);
  };

  for (const [key, code] of [
    ['AC25_TRUSTED_RESULT', 'TRUSTED_JOB_NOT_SUCCESS'],
    ['AC25_CANDIDATE_RESULT', 'CANDIDATE_JOB_NOT_SUCCESS'],
    ['AC25_INTEGRATION_RESULT', 'INTEGRATION_JOB_NOT_SUCCESS'],
  ]) {
    if (readEnv(evidence, key) !== 'success') add(code);
  }

  if (readEnv(evidence, 'AC25_TRUSTED_VERDICT') !== '1') {
    add('TRUSTED_VERDICT_NOT_PASS');
  }

  const receiptDigest = readEnv(evidence, 'AC25_RECEIPT_SHA256');
  if (!SHA256.test(receiptDigest)) add('PUBLISH_EVIDENCE_INCOMPLETE');

  const candidateCommit = readEnv(evidence, 'AC25_CANDIDATE_COMMIT');
  const candidateTree = readEnv(evidence, 'AC25_CANDIDATE_TREE');
  const mergeCommit = readEnv(evidence, 'AC25_MERGE_COMMIT');
  const mergeTree = readEnv(evidence, 'AC25_MERGE_TREE');
  const parentBase = readEnv(evidence, 'AC25_PARENT_BASE');
  const parentCandidate = readEnv(evidence, 'AC25_PARENT_CANDIDATE');

  for (const value of [candidateCommit, candidateTree, mergeCommit, mergeTree]) {
    if (!OID.test(value)) add('PUBLISH_EVIDENCE_INCOMPLETE');
  }

  if (OID.test(candidateCommit) && candidateCommit !== LOCKED_CANDIDATE_HEAD) {
    add('CANDIDATE_COORDINATE_MISMATCH');
  }
  if (OID.test(mergeCommit) && mergeCommit === LOCKED_CANDIDATE_HEAD) {
    add('MERGE_EQUALS_SCOPE_END');
  }
  if (parentBase !== LOCKED_INTEGRATION_BASE) add('MERGE_PARENT_MISMATCH');
  if (parentCandidate !== LOCKED_CANDIDATE_HEAD) add('MERGE_PARENT_MISMATCH');

  const errorCode = reasons.length === 0 ? 'OK' : reasons[0];
  return {
    conclusion: reasons.length === 0 ? 'success' : 'failure',
    errorCode: SHORT_CODE.test(errorCode) || errorCode === 'OK'
      ? errorCode
      : 'PUBLISH_EVIDENCE_INCOMPLETE',
    receiptDigest,
    candidateTree,
    mergeCommit,
    mergeTree,
    parentBase,
    parentCandidate,
  };
}

// summary 는 meta-only 다. 경로·원문·token·stack 을 넣지 않는다.
export function buildSummary(verdict, { runUrl }) {
  return [
    `verdict=${verdict.conclusion === 'success' ? 1 : 0}`,
    `error_code=${verdict.errorCode}`,
    `candidate_commit=${LOCKED_CANDIDATE_HEAD}`,
    `candidate_tree=${verdict.candidateTree || 'NONE'}`,
    `integration_base_commit=${LOCKED_INTEGRATION_BASE}`,
    `synthetic_merge_commit=${verdict.mergeCommit || 'NONE'}`,
    `synthetic_merge_tree=${verdict.mergeTree || 'NONE'}`,
    `parents=${verdict.parentBase || 'NONE'},${verdict.parentCandidate || 'NONE'}`,
    `github_merge_ref_used_for_verdict=NO`,
    `receipt_sha256=${verdict.receiptDigest || 'NONE'}`,
    `run_url=${runUrl}`,
  ].join('\n');
}

export async function publishCheck({ github, owner, repo, runUrl, evidence }) {
  assertTrustedTarget({ owner, repo, evidence });

  const verdict = evaluate(evidence);
  const runId = readEnv(evidence, 'GITHUB_RUN_ID') || '0';

  const request = {
    owner: EXPECTED_OWNER,
    repo: EXPECTED_REPO,
    name: CHECK_NAME,
    head_sha: LOCKED_CANDIDATE_HEAD,
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
