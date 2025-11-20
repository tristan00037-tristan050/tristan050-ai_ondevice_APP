/**
 * Prometheus 메트릭 수집
 *
 * @module metrics/prometheus
 */
class SimpleMetrics {
    counters = new Map();
    gauges = new Map();
    histograms = new Map();
    /**
     * 카운터 증가
     */
    increment(name, labels) {
        const key = this.getKey(name, labels);
        const current = this.counters.get(key) || 0;
        this.counters.set(key, current + 1);
    }
    /**
     * 게이지 설정
     */
    set(name, value, labels) {
        const key = this.getKey(name, labels);
        this.gauges.set(key, value);
    }
    /**
     * 히스토그램 기록
     */
    observe(name, value, labels) {
        const key = this.getKey(name, labels);
        const values = this.histograms.get(key) || [];
        values.push(value);
        // 최대 1000개 유지
        if (values.length > 1000) {
            values.shift();
        }
        this.histograms.set(key, values);
    }
    /**
     * 메트릭 키 생성
     */
    getKey(name, labels) {
        if (!labels)
            return name;
        const labelStr = Object.entries(labels)
            .sort(([a], [b]) => a.localeCompare(b))
            .map(([k, v]) => `${k}="${v}"`)
            .join(',');
        return `${name}{${labelStr}}`;
    }
    /**
     * Prometheus 형식으로 내보내기
     */
    export() {
        const lines = [];
        // 카운터
        for (const [key, value] of this.counters.entries()) {
            lines.push(`${key} ${value}`);
        }
        // 게이지
        for (const [key, value] of this.gauges.entries()) {
            lines.push(`${key} ${value}`);
        }
        // 히스토그램 (간단한 평균)
        for (const [key, values] of this.histograms.entries()) {
            if (values.length > 0) {
                const sum = values.reduce((a, b) => a + b, 0);
                const avg = sum / values.length;
                lines.push(`${key}_avg ${avg}`);
                lines.push(`${key}_count ${values.length}`);
            }
        }
        return lines.join('\n') + '\n';
    }
    /**
     * 메트릭 초기화
     */
    reset() {
        this.counters.clear();
        this.gauges.clear();
        this.histograms.clear();
    }
}
// 싱글톤 인스턴스
export const metrics = new SimpleMetrics();
/**
 * 리포트 수집률 카운터
 */
export function incrementReportIngested(tenantId) {
    metrics.increment('collector_reports_ingested_total', { tenant: tenantId });
}
/**
 * API 응답 시간 히스토그램
 */
export function observeResponseTime(endpoint, duration, status) {
    metrics.observe('collector_http_request_duration_seconds', duration / 1000, {
        endpoint,
        status: status.toString(),
    });
}
/**
 * 에러율 카운터
 */
export function incrementError(endpoint, status) {
    metrics.increment('collector_http_errors_total', {
        endpoint,
        status: status.toString(),
    });
}
/**
 * 서명 요청 수 카운터
 */
export function incrementSignRequest(tenantId) {
    metrics.increment('collector_sign_requests_total', { tenant: tenantId });
}
/**
 * 번들 다운로드 수 카운터
 */
export function incrementBundleDownload(tenantId) {
    metrics.increment('collector_bundle_downloads_total', { tenant: tenantId });
}
/**
 * 데이터베이스 연결 상태 게이지
 */
export function setDatabaseConnected(connected) {
    metrics.set('collector_database_connected', connected ? 1 : 0);
}
/**
 * 활성 리포트 수 게이지
 */
export function setActiveReports(tenantId, count) {
    metrics.set('collector_reports_active', count, { tenant: tenantId });
}
//# sourceMappingURL=prometheus.js.map