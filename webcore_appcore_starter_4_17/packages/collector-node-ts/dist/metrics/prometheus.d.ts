/**
 * Prometheus 메트릭 수집
 *
 * @module metrics/prometheus
 */
declare class SimpleMetrics {
    private counters;
    private gauges;
    private histograms;
    /**
     * 카운터 증가
     */
    increment(name: string, labels?: Record<string, string>): void;
    /**
     * 게이지 설정
     */
    set(name: string, value: number, labels?: Record<string, string>): void;
    /**
     * 히스토그램 기록
     */
    observe(name: string, value: number, labels?: Record<string, string>): void;
    /**
     * 메트릭 키 생성
     */
    private getKey;
    /**
     * Prometheus 형식으로 내보내기
     */
    export(): string;
    /**
     * 메트릭 초기화
     */
    reset(): void;
}
export declare const metrics: SimpleMetrics;
/**
 * 리포트 수집률 카운터
 */
export declare function incrementReportIngested(tenantId: string): void;
/**
 * API 응답 시간 히스토그램
 */
export declare function observeResponseTime(endpoint: string, duration: number, status: number): void;
/**
 * 에러율 카운터
 */
export declare function incrementError(endpoint: string, status: number): void;
/**
 * 서명 요청 수 카운터
 */
export declare function incrementSignRequest(tenantId: string): void;
/**
 * 번들 다운로드 수 카운터
 */
export declare function incrementBundleDownload(tenantId: string): void;
/**
 * 데이터베이스 연결 상태 게이지
 */
export declare function setDatabaseConnected(connected: boolean): void;
/**
 * 활성 리포트 수 게이지
 */
export declare function setActiveReports(tenantId: string, count: number): void;
export {};
//# sourceMappingURL=prometheus.d.ts.map