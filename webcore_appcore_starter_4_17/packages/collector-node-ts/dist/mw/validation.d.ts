/**
 * 입력 검증 강화 미들웨어
 * SQL Injection, XSS, CSRF 방지
 *
 * @module mw/validation
 */
import { Request, Response, NextFunction } from 'express';
/**
 * SQL Injection 검증
 */
export declare function validateSQLInjection(input: string): boolean;
/**
 * XSS 검증
 */
export declare function validateXSS(input: string): boolean;
/**
 * 입력 값 검증 미들웨어
 */
export declare function validateInput(req: Request, res: Response, next: NextFunction): void;
/**
 * 문자열 길이 제한 검증
 */
export declare function validateStringLength(value: string, maxLength: number, fieldName: string): {
    valid: boolean;
    error?: string;
};
/**
 * 숫자 범위 검증
 */
export declare function validateNumberRange(value: number, min: number, max: number, fieldName: string): {
    valid: boolean;
    error?: string;
};
/**
 * ID 형식 검증 (리포트 ID 등)
 */
export declare function validateIdFormat(id: string): {
    valid: boolean;
    error?: string;
};
//# sourceMappingURL=validation.d.ts.map