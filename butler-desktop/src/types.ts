export interface SSEEvent {
  type:
    | 'phase_start'
    | 'chunk_progress'
    | 'chunk_done'
    | 'reduce_start'
    | 'verify_start'
    | 'complete'
    | 'error'
    | 'cancelled'
    | 'heartbeat';
  data: Record<string, unknown>;
}

export interface EgressStats {
  task_id: string;
  mode: 'local_only' | 'network_allowed';
  egress_bytes_total: number;
  dns_requests: number;
  http_requests: number;
  https_requests: number;
  telemetry_enabled: boolean;
  crash_report_enabled: boolean;
  update_check_enabled: boolean;
  raw_text_logged: boolean;
  input_digest16: string;
  output_digest16: string;
  verdict: 'PASS' | 'FAIL';
}

export type FileGrade = 'S' | 'M' | 'L' | 'XL' | 'Media-L' | 'blocked';
