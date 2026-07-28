#!/usr/bin/env node
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { lstat, readFile, readdir, writeFile } from 'node:fs/promises';
import { basename, relative, resolve, sep } from 'node:path';

function parseArgs(argv) {
  const options = {};
  for (let index = 0; index < argv.length; index += 2) {
    const key = argv[index]?.replace(/^--/, '');
    const value = argv[index + 1];
    if (!key || !value) throw new Error('ARGUMENT_INVALID');
    options[key] = value;
  }
  return options;
}

function digest(value) {
  return createHash('sha256').update(value).digest('hex');
}

function oid(algorithm, hex) {
  const length = algorithm === 'sha256' ? 64 : algorithm === 'sha1' ? 40 : 0;
  if (!new RegExp(`^[0-9a-f]{${length}}$`).test(hex)) {
    throw new Error('OID_INVALID');
  }
  return { algorithm, hex };
}

async function regularFiles(root) {
  const output = [];
  async function walk(current) {
    for (const entry of await readdir(current, { withFileTypes: true })) {
      const path = resolve(current, entry.name);
      const info = await lstat(path);
      if (info.isSymbolicLink()) throw new Error('EVIDENCE_SYMLINK_FORBIDDEN');
      if (info.isDirectory()) {
        await walk(path);
      } else if (info.isFile()) {
        const rel = relative(root, path).split(sep).join('/');
        if (!rel || rel.startsWith('../')) throw new Error('EVIDENCE_PATH_INVALID');
        output.push({ path: rel, bytes: await readFile(path) });
      } else {
        throw new Error('EVIDENCE_SPECIAL_FILE_FORBIDDEN');
      }
    }
  }
  await walk(root);
  return output;
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  for (const key of ['package', 'repository', 'pull-request', 'head', 'tree']) {
    if (!options[key]) throw new Error(`REQUIRED_${key.toUpperCase()}_MISSING`);
  }
  const root = resolve(options.package);
  const objectFormat = execFileSync('git', ['rev-parse', '--show-object-format'], {
    encoding: 'utf8',
  }).trim();
  const actualHead = execFileSync('git', ['rev-parse', 'HEAD'], {
    encoding: 'utf8',
  }).trim();
  const actualTree = execFileSync('git', ['rev-parse', 'HEAD^{tree}'], {
    encoding: 'utf8',
  }).trim();
  if (options.head !== actualHead || options.tree !== actualTree) {
    throw new Error('CHECKOUT_IDENTITY_MISMATCH');
  }

  const files = await regularFiles(root);
  const contexts = files
    .filter(item => item.path.startsWith('contexts/') && item.path.endsWith('.json'));
  const reports = files.filter(item => item.path.startsWith('reports/'));
  if (contexts.length === 0 || reports.length === 0) {
    throw new Error('EVIDENCE_INPUT_MISSING');
  }
  const reportsByDigest = new Map();
  for (const report of reports) {
    const sha = digest(report.bytes);
    if (reportsByDigest.has(sha)) throw new Error('REPORT_DIGEST_AMBIGUOUS');
    reportsByDigest.set(sha, report.path);
  }

  const runs = [];
  let workflow = null;
  for (const file of contexts.sort((a, b) => a.path.localeCompare(b.path))) {
    const context = JSON.parse(file.bytes.toString('utf8'));
    const reportPath = reportsByDigest.get(context.report_sha256);
    if (!reportPath) throw new Error('CONTEXT_REPORT_NOT_FOUND');
    if (context.subject_pr_head !== actualHead
        || context.execution_commit !== actualHead
        || context.tree_oid?.algorithm !== objectFormat
        || context.tree_oid?.hex !== actualTree
        || context.runner_kind !== 'github-hosted'
        || context.exit_code !== 0) {
      throw new Error('CONTEXT_IDENTITY_INVALID');
    }
    const currentWorkflow = {
      runner_kind: context.runner_kind,
      run_id: context.workflow_run_id,
      run_attempt: context.workflow_run_attempt,
      workflow_ref: context.workflow_ref,
    };
    if (workflow === null) {
      workflow = currentWorkflow;
    } else if (JSON.stringify(workflow) !== JSON.stringify(currentWorkflow)) {
      throw new Error('CONTEXT_WORKFLOW_MISMATCH');
    }
    runs.push({
      runner: context.suite,
      command: context.command,
      tool_versions: context.tool_versions,
      exit_code: context.exit_code,
      started_at: context.started_at,
      finished_at: context.finished_at,
      os: context.os,
      arch: context.arch,
      execution_oid: oid(objectFormat, context.execution_commit),
      tree_oid: oid(objectFormat, context.tree_oid.hex),
      raw_result_path: reportPath,
      raw_result_sha256: context.report_sha256,
      context_path: file.path,
      context_sha256: digest(file.bytes),
    });
  }

  const index = {
    schema_version: 1,
    subject: {
      repository: options.repository,
      pull_request: Number(options['pull-request']),
      head_oid: oid(objectFormat, actualHead),
      tree_oid: oid(objectFormat, actualTree),
    },
    workflow,
    runs,
  };
  const output = resolve(root, options.output ?? 'evidence-index.json');
  await writeFile(output, `${JSON.stringify(index, null, 2)}\n`, { flag: 'wx' });
  console.log(`FIRSTSCREEN_EVIDENCE_INDEX=PASS:${basename(output)}:${runs.length}`);
}

main().catch(error => {
  console.error(`FIRSTSCREEN_EVIDENCE_INDEX=FAIL:${error.message}`);
  process.exitCode = 1;
});
