/**
 * 입력 검증 강화 미들웨어
 * SQL Injection, XSS, CSRF 방지
 *
 * @module mw/validation
 */
import { logSecurityEvent } from './audit.js';
/**
 * SQL Injection 패턴 검사
 */
const SQL_INJECTION_PATTERNS = [
    /(\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|EXECUTE|UNION|SCRIPT)\b)/i,
    /(--|;|\/\*|\*\/|xp_|sp_)/i,
    /(\b(OR|AND)\s+\d+\s*=\s*\d+)/i,
];
/**
 * XSS 패턴 검사
 */
const XSS_PATTERNS = [
    /<script[^>]*>.*?<\/script>/gi,
    /<iframe[^>]*>.*?<\/iframe>/gi,
    /javascript:/gi,
    /on\w+\s*=/gi, // onclick, onerror 등
    /<img[^>]+src[^>]*=.*javascript:/gi,
];
/**
 * SQL Injection 검증
 */
export function validateSQLInjection(input) {
    return SQL_INJECTION_PATTERNS.some(pattern => pattern.test(input));
}
/**
 * XSS 검증
 */
export function validateXSS(input) {
    return XSS_PATTERNS.some(pattern => pattern.test(input));
}
/**
 * 입력 값 검증 미들웨어
 */
export function validateInput(req, res, next) {
    // Query 파라미터 검증
    const queryString = JSON.stringify(req.query);
    if (validateSQLInjection(queryString) || validateXSS(queryString)) {
        logSecurityEvent(req, 'suspicious_activity', 'SQL Injection or XSS attempt in query parameters');
        res.status(400).json({
            error: 'Invalid input',
            message: 'Query parameters contain potentially malicious content',
        });
        return;
    }
    // Path 파라미터 검증
    const pathString = JSON.stringify(req.params);
    if (validateSQLInjection(pathString) || validateXSS(pathString)) {
        logSecurityEvent(req, 'suspicious_activity', 'SQL Injection or XSS attempt in path parameters');
        res.status(400).json({
            error: 'Invalid input',
            message: 'Path parameters contain potentially malicious content',
        });
        return;
    }
    // Body 검증 (JSON)
    if (req.body && typeof req.body === 'object') {
        const bodyString = JSON.stringify(req.body);
        if (validateSQLInjection(bodyString) || validateXSS(bodyString)) {
            logSecurityEvent(req, 'suspicious_activity', 'SQL Injection or XSS attempt in request body');
            res.status(400).json({
                error: 'Invalid input',
                message: 'Request body contains potentially malicious content',
            });
            return;
        }
    }
    next();
}
/**
 * 문자열 길이 제한 검증
 */
export function validateStringLength(value, maxLength, fieldName) {
    if (value.length > maxLength) {
        return {
            valid: false,
            error: `${fieldName} exceeds maximum length of ${maxLength} characters`,
        };
    }
    return { valid: true };
}
/**
 * 숫자 범위 검증
 */
export function validateNumberRange(value, min, max, fieldName) {
    if (value < min || value > max) {
        return {
            valid: false,
            error: `${fieldName} must be between ${min} and ${max}`,
        };
    }
    return { valid: true };
}
/**
 * ID 형식 검증 (리포트 ID 등)
 */
export function validateIdFormat(id) {
    // 리포트 ID 형식: report-{timestamp}-{random}
    const pattern = /^report-\d+-[a-z0-9]+$/i;
    if (!pattern.test(id)) {
        return {
            valid: false,
            error: 'Invalid ID format',
        };
    }
    return { valid: true };
}
//# sourceMappingURL=validation.js.map