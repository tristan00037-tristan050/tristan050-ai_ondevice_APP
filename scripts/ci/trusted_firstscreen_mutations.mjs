#!/usr/bin/env node
import { createHash } from 'node:crypto';
import { lstat, readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  calculateAccounting,
  collectNode,
  collectPytest,
  requireRepositoryPath,
  validateContext,
  validateReportBinding,
} from '../../butler-desktop/scripts/verify-required-test-nodes.mjs';
import { parseStrictJson } from './strict_json.mjs';

const SEEDS = [
  0x4255544c45523131n,
  0x4653563131455649n,
  0x5452555354474154n,
];
const CASES_PER_SEED = 1000;
const OPERATORS = [
  'key_delete',
  'key_add',
  'key_duplicate',
  'unicode_normalization',
  'path_segment',
  'integer_bool',
  'digest_flip',
  'report_context_swap',
  'runner_file_title_swap',
  'duplicated_testcase',
  'skipped_xfail',
  'xml_entity_attribute',
];

function args(argv) {
  const result = {};
  for (let index = 0; index < argv.length; index += 2) {
    const key = argv[index]?.replace(/^--/, '');
    const value = argv[index + 1];
    if (!key || !value) throw new Error('ARGUMENT_INVALID');
    result[key] = value;
  }
  return result;
}

function next(state) {
  let value = state;
  value ^= value << 13n;
  value ^= value >> 7n;
  value ^= value << 17n;
  return value & 0xffffffffffffffffn;
}

function clone(value) {
  return structuredClone(value);
}

function rejected(callback) {
  try {
    return callback() === false;
  } catch (error) {
    // v16.0 (총괄기획팀 2026-07-30): 이전 판은 어떤 예외든 catch 해 "차단(true)"으로
    // 셌다. 그 결과 검증기가 *능동적으로 거부* 한 것과 *아예 실행되지 못한 것* 을
    // 구분하지 못했다. 보호 검증기는 거부를 UPPER_SNAKE 오류코드(예: XML_PARSE_INVALID,
    // JSON_DUPLICATE_KEY, CONTEXT_IDENTITY_MISMATCH)로만 신호한다 — 이는 이 파일
    // 최상위 main().catch 의 분류 규약과 동일하다. 그 형태가 아닌 예외(TypeError
    // "x is not a function" 등 실행 실패)는 차단이 아니므로 다시 던져 호출부가
    // UNANALYSED 로 집계하게 한다(파서 subprocess 의 생존 여부는 main() 시작부의
    // 실행 통제가 별도로 증명한다).
    const code = String(error?.message ?? '');
    if (/^[A-Z0-9_]+$/.test(code)) return true;
    throw error;
  }
}

function contextExpected(metadata) {
  return {
    repository: metadata.repository,
    eventName: metadata.event_name,
    pullRequest: metadata.pull_request,
    head: metadata.subject_head,
    tree: metadata.tree_oid.hex,
    objectFormat: metadata.tree_oid.algorithm,
    runId: metadata.producer.run_id,
    runAttempt: metadata.producer.run_attempt,
    workflowRef: metadata.producer.workflow_ref,
  };
}

function mutateAndVerify(operator, canonical) {
  const {
    actual,
    context,
    expected,
    reportDigests,
    reportRunners,
    required,
  } = canonical;
  if (operator === 'key_delete') {
    const mutated = clone(context);
    delete mutated.execution_commit;
    return rejected(() => validateContext(mutated, expected));
  }
  if (operator === 'key_add') {
    const mutated = { ...clone(context), untrusted_extra: true };
    return rejected(() => validateContext(mutated, expected));
  }
  if (operator === 'key_duplicate') {
    return rejected(() => parseStrictJson(Buffer.from(
      '{"schema_version":2,"schema_version":2}',
    )));
  }
  if (operator === 'unicode_normalization') {
    return rejected(() => requireRepositoryPath('reports/e\u0301vidence.json'));
  }
  if (operator === 'path_segment') {
    return rejected(() => requireRepositoryPath('../reports/result.json'));
  }
  if (operator === 'integer_bool') {
    const mutated = { ...clone(context), run_attempt: true };
    return rejected(() => validateContext(mutated, expected));
  }
  if (operator === 'digest_flip') {
    const mutated = {
      ...clone(context),
      report_sha256: `${context.report_sha256[0] === '0' ? '1' : '0'}${
        context.report_sha256.slice(1)
      }`,
    };
    return rejected(() => validateReportBinding(
      mutated,
      reportDigests,
      reportRunners,
    ));
  }
  if (operator === 'report_context_swap') {
    const mutated = {
      ...clone(context),
      runner: context.runner === 'node' ? 'pytest' : 'node',
    };
    return rejected(() => validateReportBinding(
      mutated,
      reportDigests,
      reportRunners,
    ));
  }
  if (operator === 'runner_file_title_swap') {
    const mutated = clone(actual);
    mutated[0].title = `${mutated[0].title}-changed`;
    return !calculateAccounting(required, mutated, required.length).pass;
  }
  if (operator === 'duplicated_testcase') {
    const mutated = [...clone(actual), clone(actual[0])];
    return !calculateAccounting(required, mutated, required.length).pass;
  }
  if (operator === 'skipped_xfail') {
    const mutated = clone(actual);
    mutated[0].status = 'xfail';
    return !calculateAccounting(required, mutated, required.length).pass;
  }
  if (operator === 'xml_entity_attribute') {
    return rejected(() => collectPytest(
      '<!DOCTYPE x [<!ENTITY y "z">]><testsuite tests="1">'
      + '<testcase classname="tests.x" name="x">&y;</testcase></testsuite>',
    ));
  }
  throw new Error('UNKNOWN_OPERATOR');
}

function historicalRejected(operator, canonical) {
  const {
    actual,
    context,
    expected,
    reportDigests,
    reportRunners,
    required,
  } = canonical;
  if (operator === 'execution_commit_swap') {
    const mutated = { ...clone(context), execution_commit: 'e'.repeat(40) };
    return rejected(() => validateContext(mutated, expected));
  }
  if (operator === 'report_digest_flip') {
    return mutateAndVerify('digest_flip', canonical);
  }
  if (operator === 'duplicate_required_id') {
    const mutatedRequired = clone(required);
    mutatedRequired[1].id = mutatedRequired[0].id;
    return !calculateAccounting(mutatedRequired, actual, required.length).pass;
  }
  if (operator === 'reused_actual') {
    const mutatedRequired = clone(required);
    mutatedRequired[1] = {
      ...mutatedRequired[0],
      id: `${mutatedRequired[0].id}-SECOND`,
    };
    return !calculateAccounting(mutatedRequired, actual, required.length).pass;
  }
  if (operator === 'skipped_as_passed') {
    return mutateAndVerify('skipped_xfail', canonical);
  }
  if (operator === 'duplicate_key_context') {
    return mutateAndVerify('key_duplicate', canonical);
  }
  if (operator === 'path_traversal') {
    return rejected(() => requireRepositoryPath('../context.json'));
  }
  if (operator === 'backslash_path') {
    return rejected(() => requireRepositoryPath('reports\\result.json'));
  }
  if (operator === 'junit_doctype_entity') {
    return mutateAndVerify('xml_entity_attribute', canonical);
  }
  if (['merge_ref_as_head', 'symlink_report', 'oversized_report',
    'archive_namespace_attack'].includes(operator)) {
    throw new Error('HISTORICAL_RUNNER_MISMATCH');
  }
  throw new Error('UNKNOWN_HISTORICAL_OPERATOR');
}

async function strictFile(path, maxBytes = 4 * 1024 * 1024) {
  const metadata = await lstat(path);
  if (!metadata.isFile() || metadata.isSymbolicLink()
      || metadata.size < 1 || metadata.size > maxBytes) {
    throw new Error('INPUT_FILE_INVALID');
  }
  return parseStrictJson(await readFile(path), {
    maxBytes,
    maxDepth: 64,
    maxNodes: 1_000_000,
    maxStringChars: 1_000_000,
  });
}

async function main() {
  const options = args(process.argv.slice(2));
  for (const name of ['manifest', 'metadata', 'package', 'historical', 'output']) {
    if (!options[name]) throw new Error('REQUIRED_INPUT_MISSING');
  }
  const manifest = await strictFile(resolve(options.manifest));
  const metadata = await strictFile(resolve(options.metadata));
  const packageRoot = resolve(options.package);
  const contextNames = [
    'contexts/firstscreen-v9-unit-context.json',
    'contexts/firstscreen-v9-real-sidecar-context.json',
    'contexts/firstscreen-v9-real-sidecar-unavailable-context.json',
    'contexts/contract-context.json',
    'contexts/authorities-context.json',
    'contexts/canonical-inputs-context.json',
    'contexts/product-integration-context.json',
    'contexts/windows-trust-context.json',
    'contexts/firstscreen-v9-required-audit-context.json',
    'contexts/node-verifier-context.json',
    'contexts/node-evidence-context.json',
  ];
  const contexts = await Promise.all(
    contextNames.map(name => strictFile(resolve(packageRoot, name))),
  );
  const expected = contextExpected(metadata);
  contexts.forEach(context => validateContext(context, expected));
  const context = contexts[0];
  const reportDigests = new Set(contexts.map(item => item.report_sha256));
  const reportRunners = new Map(
    contexts.map(item => [item.report_sha256, item.runner]),
  );
  const required = manifest.tests;
  if (!Array.isArray(required) || required.length !== 92) {
    throw new Error('MANIFEST_REQUIRED_SET_INVALID');
  }
  const actual = required.map(node => ({
    runner: node.runner,
    platform: node.platform,
    file: node.file,
    title: node.title,
    status: 'passed',
  }));
  if (!calculateAccounting(required, actual, 92).pass) {
    throw new Error('BASELINE_ACCOUNTING_INVALID');
  }
  collectNode({
    schema_version: 1,
    nodes: [{ file: required[0].file, title: required[0].title, status: 'passed' }],
  });
  // v16.0 (총괄기획팀 2026-07-30) 보호 파서 실행 통제.
  // 변이 오라클은 "차단 건수 == 총건수" 로 보호 검증기의 건전성을 증명한다고
  // 주장한다. 그러나 이전 판은 파서 subprocess 실행 실패(파일 부재·비정상 종료)를
  // "차단" 으로 집계했기에, 보호 파서(trusted_parse_junit_xml.py)를 지우고 돌려도
  // 3,000 건 전부 "차단" 으로 게이트가 통과했다(거짓 음성). 아래 통제는 집계 이전에
  // 파서가 (1) 알려진 정상 JUnit 을 반드시 파싱하고(=파서 생존 증명), (2) DTD/ENTITY
  // 공격을 반드시 거부함을 요구한다. 둘 중 하나라도 어긋나면 게이트는 즉시 실패한다 —
  // 죽었거나 변조된 파서가 "완벽한 차단기" 로 위장할 수 없다.
  let parserControlNodes;
  try {
    parserControlNodes = collectPytest(
      '<testsuite name="parser-liveness-control" tests="1" failures="0" errors="0" skipped="0">'
      + '<testcase classname="tests.control" name="control"/></testsuite>',
    );
  } catch {
    throw new Error('PARSER_LIVENESS_CONTROL_FAILED');
  }
  if (!Array.isArray(parserControlNodes) || parserControlNodes.length !== 1
      || parserControlNodes[0].status !== 'passed') {
    throw new Error('PARSER_LIVENESS_CONTROL_FAILED');
  }
  if (!rejected(() => collectPytest(
    '<!DOCTYPE x [<!ENTITY y "z">]><testsuite name="parser-rejection-control" tests="1" failures="0" errors="0" skipped="0">'
    + '<testcase classname="tests.control" name="control">&y;</testcase>'
    + '</testsuite>',
  ))) {
    throw new Error('PARSER_REJECTION_CONTROL_FAILED');
  }
  const canonical = {
    actual,
    context,
    expected,
    reportDigests,
    reportRunners,
    required,
  };
  const historical = await strictFile(resolve(options.historical));
  if (historical.schema_version !== 1 || !Array.isArray(historical.cases)) {
    throw new Error('HISTORICAL_CORPUS_INVALID');
  }
  const nodeHistorical = historical.cases.filter(item => item.runner === 'node');
  const historicalIds = new Set();
  for (const item of nodeHistorical) {
    if (typeof item.id !== 'string' || historicalIds.has(item.id)
        || typeof item.operator !== 'string'
        || !historicalRejected(item.operator, canonical)) {
      throw new Error('HISTORICAL_ATTACK_ACCEPTED');
    }
    historicalIds.add(item.id);
  }

  const runs = [];
  for (const seed of SEEDS) {
    let state = seed;
    const operatorCounts = Object.fromEntries(OPERATORS.map(name => [name, 0]));
    let rejectedCases = 0;
    let acceptedMalicious = 0;
    let unanalysed = 0;
    for (let index = 0; index < CASES_PER_SEED; index += 1) {
      state = next(state);
      const operator = OPERATORS[Number(state % BigInt(OPERATORS.length))];
      operatorCounts[operator] += 1;
      try {
        if (mutateAndVerify(operator, canonical)) rejectedCases += 1;
        else acceptedMalicious += 1;
      } catch {
        // v16.0: 평가 자체가 불가능했던 변이는 UNANALYSED 다. 실행 실패를 "차단"으로
        // 세면 고장난/부재한 검증기가 완벽한 차단기로 위장한다. unanalysed !== 0 이면
        // 게이트가 실패하므로, 이 경로는 fail-closed 다. (건전한 실행에서는 각 연산자가
        // rejected()/calculateAccounting 로 불리언을 돌려주어 이 catch 에 닿지 않는다.)
        unanalysed += 1;
      }
    }
    runs.push({
      generator_version: '1',
      generator_sha256: createHash('sha256').update(
        await readFile(fileURLToPath(import.meta.url)),
      ).digest('hex'),
      seed: `0x${seed.toString(16).toUpperCase()}`,
      cases: CASES_PER_SEED,
      operator_counts: operatorCounts,
      rejected: rejectedCases,
      accepted_malicious: acceptedMalicious,
      unanalysed,
    });
  }
  const result = {
    schema_version: 1,
    seeds: runs.length,
    cases_per_seed: CASES_PER_SEED,
    total_generated_cases: runs.reduce((total, run) => total + run.cases, 0),
    accepted_malicious: runs.reduce(
      (total, run) => total + run.accepted_malicious,
      0,
    ),
    unanalysed: runs.reduce((total, run) => total + run.unanalysed, 0),
    historical_node_cases: nodeHistorical.length,
    historical_node_accepted: 0,
    runs,
  };
  if (result.total_generated_cases < 3000
      || result.accepted_malicious !== 0
      || result.unanalysed !== 0) {
    throw new Error('TRUSTED_MUTATION_GATE_FAILED');
  }
  await writeFile(
    resolve(options.output),
    `${JSON.stringify(result, null, 2)}\n`,
    { flag: 'wx' },
  );
  console.log('TRUSTED_MUTATION_GATE_OK=1');
}

main().catch(error => {
  const code = /^[A-Z0-9_]+$/.test(String(error?.message ?? ''))
    ? error.message
    : 'TRUSTED_MUTATION_GATE_FAILED';
  console.log('TRUSTED_MUTATION_GATE_OK=0');
  console.log(`ERROR_CODE=${code}`);
  process.exitCode = 1;
});
