/**
 * Policy Loader (Policy-as-Code v1)
 * 정책 파일 로드 및 검증
 */

import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

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

function loadPolicyFile(filename: string): Policy | null {
  try {
    const path = join(POLICY_DIR, filename);
    const content = readFileSync(path, 'utf8');
    
    // 간단한 YAML 파싱 (js-yaml 없이 기본 파싱)
    // 주의: 복잡한 YAML은 지원하지 않음, 기본 구조만 파싱
    const policy: any = { version: '', rules: [] };
    const lines = content.split('\n');
    let currentRule: any = null;
    let inRules = false;
    let currentKey = '';
    let currentArray: string[] = [];
    let indentLevel = 0;
    
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith('#')) continue;
      
      const currentIndent = line.length - line.trimStart().length;
      
      if (trimmed.startsWith('version:')) {
        policy.version = trimmed.split(':')[1]?.trim().replace(/['"]/g, '') || '';
      } else if (trimmed === 'rules:') {
        inRules = true;
        indentLevel = currentIndent;
      } else if (inRules && currentIndent > indentLevel) {
        if (trimmed.startsWith('- id:')) {
          // 이전 rule 저장
          if (currentRule) {
            if (currentArray.length > 0 && currentKey) {
              currentRule[currentKey] = currentArray;
              currentArray = [];
            }
            policy.rules.push(currentRule);
          }
          currentRule = {
            id: trimmed.split(':')[1]?.trim().replace(/['"]/g, '') || '',
            name: '',
            description: '',
            action: 'block',
          };
          currentKey = '';
        } else if (currentRule && trimmed.includes(':')) {
          // 이전 배열 저장
          if (currentArray.length > 0 && currentKey) {
            currentRule[currentKey] = currentArray;
            currentArray = [];
          }
          
          const [key, ...valueParts] = trimmed.split(':');
          currentKey = key.trim();
          const value = valueParts.join(':').trim().replace(/['"]/g, '');
          
          if (currentKey === 'name' || currentKey === 'description' || currentKey === 'action') {
            currentRule[currentKey] = value;
          } else if (currentKey === 'max_limit_days') {
            currentRule[currentKey] = parseInt(value, 10);
          }
        } else if (currentRule && trimmed.startsWith('- ')) {
          const item = trimmed.substring(2).trim().replace(/['"]/g, '');
          if (item) currentArray.push(item);
        }
      }
    }
    
    // 마지막 rule 저장
    if (currentRule) {
      if (currentArray.length > 0 && currentKey) {
        currentRule[currentKey] = currentArray;
      }
      policy.rules.push(currentRule);
    }
    
    return policy as Policy;
  } catch (error) {
    console.warn(`[policy] Failed to load ${filename}:`, error);
    return null;
  }
}

export function loadPolicies(): void {
  exportPolicy = loadPolicyFile('export.yaml');
  headersPolicy = loadPolicyFile('headers.yaml');
  metaOnlyPolicy = loadPolicyFile('meta_only.yaml');
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

