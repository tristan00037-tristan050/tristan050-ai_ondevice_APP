/**
 * Collector 인증/테넌트 가드 미들웨어
 * API_KEYS 환경변수로 X-Tenant ↔ API Key 매핑 검증
 *
 * @module auth
 */
import { Request, Response, NextFunction } from 'express';
/**
 * 테넌트/API Key 검증 미들웨어
 * X-Tenant와 X-Api-Key 헤더를 검증하여 테넌트 격리 보장
 */
export declare function requireTenantAuth(req: Request, res: Response, next: NextFunction): void;
/**
 * 서명 토큰 검증 (bundle.zip 다운로드용)
 * 토큰 내 tenant/id와 요청 파라미터 교차검증
 */
export declare function verifySignToken(req: Request, res: Response, next: NextFunction): void;
//# sourceMappingURL=auth.d.ts.map