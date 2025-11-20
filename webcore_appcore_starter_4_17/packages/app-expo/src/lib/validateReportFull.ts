/**
 * Ajv 기반 풀 스키마 검증 (앱 런타임)
 * 경량 검증(validateReportLite)을 Ajv 풀 검증으로 교체
 * 
 * @module validateReportFull
 */

import Ajv from 'ajv';
import addFormats from 'ajv-formats';
// 스키마는 런타임에 로드하거나 별도 모듈로 제공
// import qcReportSchema from '../../../contracts/qc_report.schema.json';

// 스키마를 동적으로 로드하는 헬퍼 함수
async function loadSchema(): Promise<unknown> {
  // 실제 구현에서는 스키마 파일을 로드하거나
  // 빌드 타임에 번들에 포함
  // 여기서는 예시로 require 또는 fetch 사용
  try {
    // React Native에서는 require 사용 가능
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    return require('../../../contracts/qc_report.schema.json');
  } catch {
    // 또는 fetch로 로드
    const response = await fetch('/contracts/qc_report.schema.json');
    return response.json();
  }
}

// Ajv 싱글턴 인스턴스 (재사용)
const ajv = new Ajv({
  allErrors: true,
  verbose: true,
  strict: true,
  validateFormats: true,
  removeAdditional: false,
});
addFormats(ajv);

// 스키마 컴파일 (지연 로딩, 싱글턴)
let validate: Ajv.ValidateFunction | null = null;
let schemaPromise: Promise<unknown> | null = null;

async function getValidator(): Promise<Ajv.ValidateFunction> {
  if (validate) {
    return validate;
  }
  
  if (!schemaPromise) {
    schemaPromise = loadSchema();
  }
  
  const schema = await schemaPromise;
  validate = ajv.compile(schema);
  return validate;
}

export interface ValidationResult {
  valid: boolean;
  schema_version?: string; // 스키마 버전 (옵션, 불일치 탐지 대비)
  errors?: Array<{
    instancePath: string;
    schemaPath: string;
    keyword: string;
    params: Record<string, unknown>;
    message?: string;
  }>;
}

/**
 * 리포트를 Ajv 풀 스키마로 검증 (비동기)
 * 
 * @param report - 검증할 QuickCheck 리포트 객체
 * @returns 검증 결과 (valid: true/false, errors: 에러 배열)
 */
export async function validateReportFull(report: unknown): Promise<ValidationResult> {
  const validator = await getValidator();
  const valid = validator(report);
  
  if (!valid) {
    return {
      valid: false,
      errors: validator.errors || [],
    };
  }
  
  return { valid: true };
}

/**
 * 리포트 검증 (간편 버전 - boolean만 반환, 비동기)
 * 
 * @param report - 검증할 QuickCheck 리포트 객체
 * @returns 검증 통과 여부
 */
export async function isValidReport(report: unknown): Promise<boolean> {
  const result = await validateReportFull(report);
  return result.valid;
}

/**
 * 리포트 검증 및 에러 메시지 반환 (비동기)
 * 
 * @param report - 검증할 QuickCheck 리포트 객체
 * @returns 에러 메시지 배열 (검증 통과 시 빈 배열)
 */
export async function validateReportWithMessages(report: unknown): Promise<string[]> {
  const result = await validateReportFull(report);
  
  if (result.valid) {
    return [];
  }
  
  return (result.errors || []).map(err => {
    const path = err.instancePath || '/';
    const message = err.message || 'Validation error';
    return `${path}: ${message}`;
  });
}

