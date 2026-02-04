/**
 * Policy Loader (Policy-as-Code v1)
 * 검증된 YAML 파서 + 스키마 검증 (Fail-Closed)
 * SSOT v3.4: meta-only 에러 출력 (경로/버전/규칙ID/에러코드만)
 */

import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import yaml from 'js-yaml';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const ROOT_DIR = join(__dirname, '../../../../..');
const POLICY_DIR = join(ROOT_DIR, 'policy');

export interface PolicyRule {
  id: string;
  name: string;
  description: string;
  action: 'block' | 'allow' | 'audit';
  forbidden_fields?: string[];
  required_headers?: string[];
  optional_headers?: string[];
  allowed_fields?: string[];
  max_limit_days?: number;
}

export interface Policy {
  version: string;
  rules: PolicyRule[];
}

let exportPolicy: Policy | null = null;
let headersPolicy: Policy | null = null;
let metaOnlyPolicy: Policy | null = null;

/**
 * Policy 스키마 검증 (Fail-Closed)
 * 필수 키 누락/타입 불일치/버전 키 누락은 모두 Fail-Closed
 */
function validatePolicySchema(data: any, filepath: string): { valid: boolean; error_code?: string } {
  // 버전 키 필수
  if (!data || typeof data !== 'object') {
    return { valid: false, error_code: 'INVALID_ROOT_TYPE' };
  }

  if (!('version' in data)) {
    return { valid: false, error_code: 'MISSING_VERSION_KEY' };
  }

  if (typeof data.version !== 'string' || !data.version.trim()) {
    return { valid: false, error_code: 'INVALID_VERSION_TYPE' };
  }

  // rules 키 필수
  if (!('rules' in data)) {
    return { valid: false, error_code: 'MISSING_RULES_KEY' };
  }

  if (!Array.isArray(data.rules)) {
    return { valid: false, error_code: 'INVALID_RULES_TYPE' };
  }

  // 각 rule 검증
  for (let i = 0; i < data.rules.length; i++) {
    const rule = data.rules[i];
    if (!rule || typeof rule !== 'object') {
      return { valid: false, error_code: `INVALID_RULE_TYPE_AT_INDEX_${i}` };
    }

    // 필수 키 검증
    if (!('id' in rule) || typeof rule.id !== 'string' || !rule.id.trim()) {
      return { valid: false, error_code: `MISSING_RULE_ID_AT_INDEX_${i}` };
    }

    if (!('name' in rule) || typeof rule.name !== 'string') {
      return { valid: false, error_code: `MISSING_RULE_NAME_AT_INDEX_${i}` };
    }

    if (!('description' in rule) || typeof rule.description !== 'string') {
      return { valid: false, error_code: `MISSING_RULE_DESCRIPTION_AT_INDEX_${i}` };
    }

    if (!('action' in rule) || !['block', 'allow', 'audit'].includes(rule.action)) {
      return { valid: false, error_code: `INVALID_RULE_ACTION_AT_INDEX_${i}` };
    }

    // 선택적 필드 타입 검증
    if ('forbidden_fields' in rule && !Array.isArray(rule.forbidden_fields)) {
      return { valid: false, error_code: `INVALID_FORBIDDEN_FIELDS_TYPE_AT_INDEX_${i}` };
    }

    if ('required_headers' in rule && !Array.isArray(rule.required_headers)) {
      return { valid: false, error_code: `INVALID_REQUIRED_HEADERS_TYPE_AT_INDEX_${i}` };
    }

    if ('optional_headers' in rule && !Array.isArray(rule.optional_headers)) {
      return { valid: false, error_code: `INVALID_OPTIONAL_HEADERS_TYPE_AT_INDEX_${i}` };
    }

    if ('allowed_fields' in rule && !Array.isArray(rule.allowed_fields)) {
      return { valid: false, error_code: `INVALID_ALLOWED_FIELDS_TYPE_AT_INDEX_${i}` };
    }

    if ('max_limit_days' in rule && typeof rule.max_limit_days !== 'number') {
      return { valid: false, error_code: `INVALID_MAX_LIMIT_DAYS_TYPE_AT_INDEX_${i}` };
    }
  }

  return { valid: true };
}

/**
 * Policy 파일 로드 (검증된 YAML 파서 + 스키마 검증)
 * Fail-Closed: 파싱 실패/스키마 실패 시 즉시 차단
 */
function loadPolicyFile(filename: string): Policy | null {
  const filepath = join(POLICY_DIR, filename);
  
  try {
    const content = readFileSync(filepath, 'utf8');
    
    // 검증된 YAML 파서 사용
    let data: any;
    try {
      data = yaml.load(content);
    } catch (parseError: any) {
      // 파싱 실패: meta-only 에러 출력 (본문 출력 금지)
      const errorCode = parseError.name === 'YAMLException' ? 'YAML_PARSE_ERROR' : 'YAML_UNKNOWN_ERROR';
      console.error('[policy] YAML parse failed:', {
        filepath,
        error_code: errorCode,
        line: parseError.mark?.line,
        column: parseError.mark?.column,
      });
      // Fail-Closed: 파싱 실패 시 null 반환 (차단)
      return null;
    }

    // 스키마 검증
    const schemaResult = validatePolicySchema(data, filepath);
    if (!schemaResult.valid) {
      // 스키마 실패: meta-only 에러 출력 (본문 출력 금지)
      console.error('[policy] Schema validation failed:', {
        filepath,
        error_code: schemaResult.error_code,
        version: data?.version || 'MISSING',
      });
      // Fail-Closed: 스키마 실패 시 null 반환 (차단)
      return null;
    }

    return data as Policy;
  } catch (error: any) {
    // 파일 읽기 실패: meta-only 에러 출력 (본문 출력 금지)
    const errorCode = error.code === 'ENOENT' ? 'FILE_NOT_FOUND' : 'FILE_READ_ERROR';
    console.error('[policy] File load failed:', {
      filepath,
      error_code: errorCode,
    });
    // Fail-Closed: 파일 읽기 실패 시 null 반환 (차단)
    return null;
  }
}

export function loadPolicies(): void {
  exportPolicy = loadPolicyFile('export.yaml');
  headersPolicy = loadPolicyFile('headers.yaml');
  metaOnlyPolicy = loadPolicyFile('meta_only.yaml');
  
  // Fail-Closed: 정책 로드 실패 시 경고 (본문 출력 금지, meta-only)
  if (!exportPolicy) {
    console.error('[policy] Policy load failed:', {
      filepath: join(POLICY_DIR, 'export.yaml'),
      error_code: 'POLICY_LOAD_FAILED',
    });
  }
  if (!headersPolicy) {
    console.error('[policy] Policy load failed:', {
      filepath: join(POLICY_DIR, 'headers.yaml'),
      error_code: 'POLICY_LOAD_FAILED',
    });
  }
  if (!metaOnlyPolicy) {
    console.error('[policy] Policy load failed:', {
      filepath: join(POLICY_DIR, 'meta_only.yaml'),
      error_code: 'POLICY_LOAD_FAILED',
    });
  }
}

export function getExportPolicy(): Policy | null {
  if (!exportPolicy) {
    loadPolicies();
  }
  return exportPolicy;
}

export function getHeadersPolicy(): Policy | null {
  if (!headersPolicy) {
    loadPolicies();
  }
  return headersPolicy;
}

export function getMetaOnlyPolicy(): Policy | null {
  if (!metaOnlyPolicy) {
    loadPolicies();
  }
  return metaOnlyPolicy;
}
