/**
 * Prometheus 메트릭 수집
 * 
 * @module metrics/prometheus
 */

// 간단한 메트릭 수집기 (실제로는 prom-client 사용 권장)
interface MetricValue {
  value: number;
  labels?: Record<string, string>;
}

class SimpleMetrics {
  private counters: Map<string, number> = new Map();
  private gauges: Map<string, number> = new Map();
  private histograms: Map<string, number[]> = new Map();

  /**
   * 카운터 증가
   */
  increment(name: string, labels?: Record<string, string>): void {
    const key = this.getKey(name, labels);
    const current = this.counters.get(key) || 0;
    this.counters.set(key, current + 1);
  }

  /**
   * 게이지 설정
   */
  set(name: string, value: number, labels?: Record<string, string>): void {
    const key = this.getKey(name, labels);
    this.gauges.set(key, value);
  }

  /**
   * 히스토그램 기록
   */
  observe(name: string, value: number, labels?: Record<string, string>): void {
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
  private getKey(name: string, labels?: Record<string, string>): string {
    if (!labels) return name;
    const labelStr = Object.entries(labels)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([k, v]) => `${k}="${v}"`)
      .join(',');
    return `${name}{${labelStr}}`;
  }

  /**
   * Prometheus 형식으로 내보내기
   */
  export(): string {
    const lines: string[] = [];

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
  reset(): void {
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
export function incrementReportIngested(tenantId: string): void {
  metrics.increment('collector_reports_ingested_total', { tenant: tenantId });
}

/**
 * API 응답 시간 히스토그램
 */
export function observeResponseTime(endpoint: string, duration: number, status: number): void {
  metrics.observe('collector_http_request_duration_seconds', duration / 1000, {
    endpoint,
    status: status.toString(),
  });
}

/**
 * 에러율 카운터
 */
export function incrementError(endpoint: string, status: number): void {
  metrics.increment('collector_http_errors_total', {
    endpoint,
    status: status.toString(),
  });
}

/**
 * 서명 요청 수 카운터
 */
export function incrementSignRequest(tenantId: string): void {
  metrics.increment('collector_sign_requests_total', { tenant: tenantId });
}

/**
 * 번들 다운로드 수 카운터
 */
export function incrementBundleDownload(tenantId: string): void {
  metrics.increment('collector_bundle_downloads_total', { tenant: tenantId });
}

/**
 * 데이터베이스 연결 상태 게이지
 */
export function setDatabaseConnected(connected: boolean): void {
  metrics.set('collector_database_connected', connected ? 1 : 0);
}

/**
 * 활성 리포트 수 게이지
 */
export function setActiveReports(tenantId: string, count: number): void {
  metrics.set('collector_reports_active', count, { tenant: tenantId });
}


