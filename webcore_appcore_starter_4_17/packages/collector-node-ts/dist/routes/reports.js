/**
 * Collector Reports 엔드포인트
 * 데이터베이스 기반 저장소 사용
 * ETag/If-None-Match 지원으로 폴링 비용 절감
 *
 * @module reports
 */
import { Router } from 'express';
import crypto from 'node:crypto';
import { requireTenantAuth, verifySignToken } from '../mw/auth.js';
import * as reportsDb from '../db/reports.js';
import * as signHistoryDb from '../db/signHistory.js';
import * as signTokenCacheDb from '../db/signTokenCache.js';
import { observeResponseTime, incrementError, incrementBundleDownload } from '../metrics/prometheus.js';
import { getCachedReportsList, setCachedReportsList } from '../cache/reports.js';
import { validateIdFormat } from '../mw/validation.js';
const router = Router();
/**
 * ETag 생성 (콘텐츠 해시 기반)
 */
function generateETag(content) {
    const hash = crypto.createHash('md5').update(content).digest('hex');
    return `"${hash}"`;
}
/**
 * 리포트 목록 조회 (서버 측 필터링, ETag 지원, 정렬 고정으로 안정성 보장)
 * GET /reports?severity=block&policy_version=v1&since=1234567890&page=1&limit=20
 */
router.get('/', requireTenantAuth, async (req, res) => {
    const startTime = Date.now();
    try {
        const tenantId = req.tenantId;
        if (!tenantId) {
            observeResponseTime('/reports', Date.now() - startTime, 401);
            incrementError('/reports', 401);
            return res.status(401).json({ error: 'Tenant ID not found' });
        }
        // Query Parameter 파싱
        const severity = req.query.severity;
        const policyVersion = req.query.policy_version;
        const since = req.query.since ? parseInt(req.query.since) : undefined;
        const page = req.query.page ? parseInt(req.query.page) : 1;
        const limit = req.query.limit ? parseInt(req.query.limit) : 20;
        // 유효성 검증
        if (severity && !['info', 'warn', 'block'].includes(severity)) {
            return res.status(400).json({ error: 'Invalid severity value. Must be info, warn, or block' });
        }
        if (page < 1) {
            return res.status(400).json({ error: 'Page must be >= 1' });
        }
        if (limit < 1 || limit > 100) {
            return res.status(400).json({ error: 'Limit must be between 1 and 100' });
        }
        // 캐시 키 생성
        const cacheKey = {
            tenantId,
            severity,
            policyVersion,
            since,
            page,
            limit,
        };
        // 캐시 조회
        const cached = getCachedReportsList(cacheKey);
        if (cached) {
            // If-None-Match 헤더 확인
            const ifNoneMatch = req.headers['if-none-match'];
            if (ifNoneMatch === cached.etag) {
                observeResponseTime('/reports', Date.now() - startTime, 304);
                return res.status(304).end();
            }
            // 캐시된 데이터 반환
            res.set({
                'ETag': cached.etag,
                'Cache-Control': 'private, must-revalidate',
            });
            observeResponseTime('/reports', Date.now() - startTime, 200);
            return res.json({
                reports: cached.reports,
                pagination: {
                    page,
                    limit,
                    totalCount: cached.totalCount,
                    totalPages: Math.ceil(cached.totalCount / limit),
                },
            });
        }
        // 데이터베이스에서 리포트 목록 조회 (서버 측 필터링)
        const { reports: tenantReports, totalCount } = await reportsDb.listReports(tenantId, {
            severity: severity,
            policyVersion,
            since,
        }, { page, limit });
        // ETag 생성 (필터링 및 페이지네이션 결과 기반)
        const content = JSON.stringify({
            reports: tenantReports,
            page,
            limit,
            totalCount,
        });
        const etag = generateETag(content);
        // 캐시 저장
        setCachedReportsList(cacheKey, {
            reports: tenantReports,
            totalCount,
            etag,
        });
        // If-None-Match 헤더 확인
        const ifNoneMatch = req.headers['if-none-match'];
        if (ifNoneMatch === etag) {
            // 콘텐츠 변경 없음 - 304 Not Modified
            return res.status(304).end();
        }
        // ETag 헤더 설정 및 응답
        res.set({
            'ETag': etag,
            'Cache-Control': 'private, must-revalidate',
        });
        res.json({
            reports: tenantReports,
            pagination: {
                page,
                limit,
                totalCount,
                totalPages: Math.ceil(totalCount / limit),
            },
        });
        observeResponseTime('/reports', Date.now() - startTime, 200);
    }
    catch (error) {
        console.error('Error fetching reports:', error);
        observeResponseTime('/reports', Date.now() - startTime, 500);
        incrementError('/reports', 500);
        res.status(500).json({ error: 'Internal server error' });
    }
});
/**
 * 리포트 상세 조회 (ETag 지원)
 * GET /reports/:id
 */
router.get('/:id', requireTenantAuth, async (req, res) => {
    try {
        const tenantId = req.tenantId;
        if (!tenantId) {
            return res.status(401).json({ error: 'Tenant ID not found' });
        }
        const { id } = req.params;
        // ID 형식 검증
        const idValidation = validateIdFormat(id);
        if (!idValidation.valid) {
            return res.status(400).json({ error: idValidation.error });
        }
        const report = await reportsDb.getReport(id, tenantId);
        if (!report) {
            return res.status(404).json({ error: 'Report not found' });
        }
        // ETag 생성
        const content = JSON.stringify(report);
        const etag = generateETag(content);
        // If-None-Match 헤더 확인
        const ifNoneMatch = req.headers['if-none-match'];
        if (ifNoneMatch === etag) {
            return res.status(304).end();
        }
        // ETag 헤더 설정 및 응답
        res.set({
            'ETag': etag,
            'Cache-Control': 'private, must-revalidate',
        });
        res.json(report);
    }
    catch (error) {
        console.error('Error fetching report:', error);
        res.status(500).json({ error: 'Internal server error' });
    }
});
// 서명 토큰 캐시 (멱등성 보장)
const signTokenCache = new Map();
const signHistory = [];
/**
 * 리포트 서명 요청 (멱등성 보장)
 * POST /reports/:id/sign
 */
router.post('/:id/sign', requireTenantAuth, async (req, res) => {
    const startTime = Date.now();
    try {
        const tenantId = req.tenantId;
        if (!tenantId) {
            return res.status(401).json({ error: 'Tenant ID not found' });
        }
        const { id } = req.params;
        const report = await reportsDb.getReport(id, tenantId);
        if (!report) {
            return res.status(404).json({ error: 'Report not found' });
        }
        // 캐시 키 (멱등성 보장)
        const cacheKey = `${tenantId}:${id}`;
        const cached = await signTokenCacheDb.getTokenCache(cacheKey);
        const issuedAt = Date.now();
        const requestedBy = tenantId; // 실제로는 req.user?.id 등 사용 가능
        // 유효기간 내 동일 요청 시 기존 토큰 재사용 (멱등성)
        if (cached && cached.expiresAt > Date.now()) {
            // 기존 토큰 재사용 시에도 이력 기록 (멱등성 요청)
            await signHistoryDb.saveSignHistory({
                reportId: id,
                tenantId,
                requestedBy,
                token: cached.token,
                issuedAt,
                expiresAt: cached.expiresAt,
                createdAt: issuedAt,
            });
            return res.json({
                token: cached.token,
                expiresAt: cached.expiresAt,
                issuedAt,
                bundleUrl: `/reports/${id}/bundle.zip?token=${cached.token}`,
            });
        }
        // 새 토큰 생성
        const signSecret = process.env.EXPORT_SIGN_SECRET || 'dev-secret';
        const expiresAt = issuedAt + 3600000; // 1시간
        const tokenPayload = {
            reportId: id,
            tenantId, // tenant 포함
            expiresAt,
        };
        // 페이로드를 base64로 인코딩
        const payloadBase64 = Buffer.from(JSON.stringify(tokenPayload)).toString('base64');
        // 서명 생성 (HMAC-SHA256)
        const signature = crypto
            .createHmac('sha256', signSecret)
            .update(payloadBase64)
            .digest('hex');
        // 토큰 형식: base64(payload).signature
        const token = `${payloadBase64}.${signature}`;
        // 캐시에 저장 (데이터베이스)
        await signTokenCacheDb.setTokenCache({
            cacheKey,
            token,
            expiresAt,
            createdAt: issuedAt,
        });
        // 서명 이력 저장 (데이터베이스)
        await signHistoryDb.saveSignHistory({
            reportId: id,
            tenantId,
            requestedBy,
            token,
            issuedAt,
            expiresAt,
            createdAt: issuedAt,
        });
        res.json({
            token,
            expiresAt,
            issuedAt,
            bundleUrl: `/reports/${id}/bundle.zip?token=${token}`,
        });
    }
    catch (error) {
        console.error('Error signing report:', error);
        res.status(500).json({ error: 'Internal server error' });
    }
});
/**
 * 서명 이력 조회 (감사 로그)
 * GET /reports/:id/sign-history
 */
router.get('/:id/sign-history', requireTenantAuth, async (req, res) => {
    try {
        const tenantId = req.tenantId;
        if (!tenantId) {
            return res.status(401).json({ error: 'Tenant ID not found' });
        }
        const { id } = req.params;
        const report = await reportsDb.getReport(id, tenantId);
        if (!report) {
            return res.status(404).json({ error: 'Report not found' });
        }
        // 데이터베이스에서 서명 이력 조회
        const history = await signHistoryDb.getSignHistory(id, tenantId);
        res.json({
            reportId: id,
            history,
            count: history.length,
        });
    }
    catch (error) {
        console.error('Error fetching sign history:', error);
        res.status(500).json({ error: 'Internal server error' });
    }
});
/**
 * 번들 메타 정보 조회
 * GET /reports/:id/bundle-meta
 */
router.get('/:id/bundle-meta', requireTenantAuth, async (req, res) => {
    try {
        const tenantId = req.tenantId;
        if (!tenantId) {
            return res.status(401).json({ error: 'Tenant ID not found' });
        }
        const { id } = req.params;
        const report = await reportsDb.getReport(id, tenantId);
        if (!report) {
            return res.status(404).json({ error: 'Report not found' });
        }
        // 번들 구성 파일 목록
        const files = [
            { name: 'qc_report.json', size: JSON.stringify(report.report).length },
            ...(report.markdown ? [{ name: 'qc_report.md', size: report.markdown.length }] : []),
        ];
        // 체크섬 계산
        const reportJson = JSON.stringify(report.report);
        const reportChecksum = crypto.createHash('sha256').update(reportJson).digest('hex');
        const markdownChecksum = report.markdown
            ? crypto.createHash('sha256').update(report.markdown).digest('hex')
            : null;
        // 총 크기 계산 (ZIP 오버헤드 포함 추정)
        const totalSize = files.reduce((sum, f) => sum + f.size, 0);
        const estimatedZipSize = Math.ceil(totalSize * 1.1); // 10% 오버헤드 추정
        const bundleMeta = {
            reportId: id,
            files: files.map(f => ({
                name: f.name,
                size: f.size,
                checksum: f.name.endsWith('.json') ? reportChecksum : markdownChecksum,
            })),
            totalFiles: files.length,
            totalSize,
            estimatedZipSize,
            checksums: {
                'qc_report.json': reportChecksum,
                ...(markdownChecksum ? { 'qc_report.md': markdownChecksum } : {}),
            },
            createdAt: report.createdAt,
            updatedAt: report.updatedAt,
        };
        res.json(bundleMeta);
    }
    catch (error) {
        console.error('Error fetching bundle meta:', error);
        res.status(500).json({ error: 'Internal server error' });
    }
});
/**
 * 리포트 번들 다운로드 (서명 토큰 검증 + tenant/id 교차검증)
 * GET /reports/:id/bundle.zip
 */
router.get('/:id/bundle.zip', verifySignToken, async (req, res) => {
    const startTime = Date.now();
    try {
        const tenantId = req.tenantId;
        const reportId = req.reportId;
        const { id } = req.params;
        if (!tenantId || !reportId) {
            observeResponseTime('/reports/:id/bundle.zip', Date.now() - startTime, 401);
            incrementError('/reports/:id/bundle.zip', 401);
            return res.status(401).json({ error: 'Tenant ID or Report ID not found' });
        }
        // 토큰 검증은 미들웨어에서 완료
        // tenant/id 교차검증
        if (id !== reportId) {
            observeResponseTime('/reports/:id/bundle.zip', Date.now() - startTime, 403);
            incrementError('/reports/:id/bundle.zip', 403);
            return res.status(403).json({ error: 'Report ID mismatch' });
        }
        const report = await reportsDb.getReport(id, tenantId);
        if (!report) {
            observeResponseTime('/reports/:id/bundle.zip', Date.now() - startTime, 404);
            incrementError('/reports/:id/bundle.zip', 404);
            return res.status(404).json({ error: 'Report not found' });
        }
        incrementBundleDownload(tenantId);
        observeResponseTime('/reports/:id/bundle.zip', Date.now() - startTime, 200);
        // ZIP 번들 생성 (실제로는 파일 시스템에서 읽기)
        // 여기서는 예시로 JSON 응답
        res.set({
            'Content-Type': 'application/zip',
            'Content-Disposition': `attachment; filename="qc_report_${id}.zip"`,
        });
        // 실제로는 ZIP 파일 스트림 전송
        res.json({
            message: 'Bundle ZIP file would be sent here',
            reportId: id,
        });
    }
    catch (error) {
        console.error('Error downloading bundle:', error);
        observeResponseTime('/reports/:id/bundle.zip', Date.now() - startTime, 500);
        incrementError('/reports/:id/bundle.zip', 500);
        res.status(500).json({ error: 'Internal server error' });
    }
});
// 레거시 호환성: reports Map export 제거 (데이터베이스 사용)
// 기존 코드와의 호환성을 위해 빈 Map export (deprecated)
export const reports = new Map();
export default router;
//# sourceMappingURL=reports.js.map