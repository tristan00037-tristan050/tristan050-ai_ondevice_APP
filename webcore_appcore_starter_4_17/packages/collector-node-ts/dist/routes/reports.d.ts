/**
 * Collector Reports 엔드포인트
 * 데이터베이스 기반 저장소 사용
 * ETag/If-None-Match 지원으로 폴링 비용 절감
 *
 * @module reports
 */
import type { Report } from '../db/reports.js';
declare const router: import("express-serve-static-core").Router;
export declare const reports: Map<string, Report>;
export default router;
//# sourceMappingURL=reports.d.ts.map