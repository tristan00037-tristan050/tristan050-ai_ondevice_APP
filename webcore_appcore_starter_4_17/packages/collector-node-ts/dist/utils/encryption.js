/**
 * 암호화 유틸리티
 * 민감 데이터 암호화 (at rest, in transit)
 *
 * @module utils/encryption
 */
import crypto from 'node:crypto';
const ALGORITHM = 'aes-256-gcm';
const IV_LENGTH = 16;
const SALT_LENGTH = 64;
const TAG_LENGTH = 16;
/**
 * 암호화 키 생성 (환경 변수에서 읽기)
 */
function getEncryptionKey() {
    const key = process.env.ENCRYPTION_KEY;
    if (!key) {
        throw new Error('ENCRYPTION_KEY environment variable is required');
    }
    // 32바이트 키 생성 (SHA256 해시 사용)
    return crypto.createHash('sha256').update(key).digest();
}
/**
 * 데이터 암호화
 */
export function encrypt(data) {
    const key = getEncryptionKey();
    const iv = crypto.randomBytes(IV_LENGTH);
    const cipher = crypto.createCipheriv(ALGORITHM, key, iv);
    let encrypted = cipher.update(data, 'utf8', 'hex');
    encrypted += cipher.final('hex');
    const tag = cipher.getAuthTag();
    // IV + Tag + Encrypted Data 형식으로 반환
    return `${iv.toString('hex')}:${tag.toString('hex')}:${encrypted}`;
}
/**
 * 데이터 복호화
 */
export function decrypt(encryptedData) {
    const key = getEncryptionKey();
    const parts = encryptedData.split(':');
    if (parts.length !== 3) {
        throw new Error('Invalid encrypted data format');
    }
    const iv = Buffer.from(parts[0], 'hex');
    const tag = Buffer.from(parts[1], 'hex');
    const encrypted = parts[2];
    const decipher = crypto.createDecipheriv(ALGORITHM, key, iv);
    decipher.setAuthTag(tag);
    let decrypted = decipher.update(encrypted, 'hex', 'utf8');
    decrypted += decipher.final('utf8');
    return decrypted;
}
/**
 * API Key 암호화 저장 (해시)
 */
export function hashApiKey(apiKey) {
    return crypto.createHash('sha256').update(apiKey).digest('hex');
}
/**
 * API Key 검증 (해시 비교)
 */
export function verifyApiKey(apiKey, hashedKey) {
    const hash = hashApiKey(apiKey);
    return crypto.timingSafeEqual(Buffer.from(hash), Buffer.from(hashedKey));
}
/**
 * 안전한 랜덤 문자열 생성
 */
export function generateSecureRandom(length = 32) {
    return crypto.randomBytes(length).toString('hex');
}
/**
 * HMAC 서명 생성
 */
export function createHMAC(data, secret) {
    return crypto.createHmac('sha256', secret).update(data).digest('hex');
}
/**
 * HMAC 서명 검증
 */
export function verifyHMAC(data, signature, secret) {
    const expectedSignature = createHMAC(data, secret);
    return crypto.timingSafeEqual(Buffer.from(signature), Buffer.from(expectedSignature));
}
//# sourceMappingURL=encryption.js.map