/**
 * 암호화 유틸리티
 * 민감 데이터 암호화 (at rest, in transit)
 *
 * @module utils/encryption
 */
/**
 * 데이터 암호화
 */
export declare function encrypt(data: string): string;
/**
 * 데이터 복호화
 */
export declare function decrypt(encryptedData: string): string;
/**
 * API Key 암호화 저장 (해시)
 */
export declare function hashApiKey(apiKey: string): string;
/**
 * API Key 검증 (해시 비교)
 */
export declare function verifyApiKey(apiKey: string, hashedKey: string): boolean;
/**
 * 안전한 랜덤 문자열 생성
 */
export declare function generateSecureRandom(length?: number): string;
/**
 * HMAC 서명 생성
 */
export declare function createHMAC(data: string, secret: string): string;
/**
 * HMAC 서명 검증
 */
export declare function verifyHMAC(data: string, signature: string, secret: string): boolean;
//# sourceMappingURL=encryption.d.ts.map