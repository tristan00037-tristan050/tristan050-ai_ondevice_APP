import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { CompanyFormatConsole } from '../components/v1_1/CompanyFormatConsole';
import {
  ADMIN_POLICY_ENDPOINTS,
  ADMIN_POLICY_SIDECAR_ORIGIN,
  FORMAT_KIND_LABELS,
  FORMAT_KINDS,
} from '../lib/admin_policy/contracts';

const DIGEST = 'sha256:' + 'b'.repeat(64);
const RAW_TEMPLATE = 'CONFIDENTIAL_COMPANY_FORMAT_SENTINEL';

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('CompanyFormatConsole v1.2', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('posts raw template only to 127.0.0.1 #772 company-format endpoint and clears runtime state after success', async () => {
    const fetcher = vi.spyOn(global, 'fetch').mockResolvedValue(
      jsonResponse({
        schema_version: 'admin.company_format_register.response.v1',
        format_id: 'format-001',
        format_digest: DIGEST,
        template_digest: DIGEST,
        template_ref: 'local-vault://formats/templates/template-001',
        audit_ref: DIGEST,
        encrypted_store: true,
        raw_saved_zero: true,
        raw_text_logged: false,
      }),
    );

    render(<CompanyFormatConsole onClose={() => undefined} />);

    fireEvent.change(screen.getByLabelText('Admin ID digest'), { target: { value: DIGEST } });
    fireEvent.change(screen.getByLabelText('Admin session digest'), { target: { value: DIGEST } });
    fireEvent.change(screen.getByLabelText('양식 제목'), { target: { value: '보고서 양식' } });
    fireEvent.change(screen.getByLabelText('부서 digest'), { target: { value: DIGEST } });
    fireEvent.change(screen.getByLabelText('양식 원문'), { target: { value: RAW_TEMPLATE } });
    fireEvent.click(screen.getByRole('button', { name: '양식 등록' }));

    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));
    const [url, init] = fetcher.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${ADMIN_POLICY_SIDECAR_ORIGIN}${ADMIN_POLICY_ENDPOINTS.registerFormat}`);
    expect((init.headers as Record<string, string>)['X-Admin-Role']).toBe('admin');
    expect(String(init.body)).toContain(RAW_TEMPLATE);
    const success = await screen.findByTestId('company-format-success');
    expect(success).toHaveTextContent('회사 양식 등록 완료');
    expect(success).not.toHaveTextContent('local-vault://formats/templates/template-001');
    expect(success).not.toHaveTextContent(/sha256:|format_digest|template_digest|template_ref/i);
    await waitFor(() => expect(screen.getByLabelText('양식 원문')).toHaveValue(''));
    expect(screen.queryByDisplayValue(RAW_TEMPLATE)).not.toBeInTheDocument();
  });

  it('does not show developer notes, vault, endpoint, or digest copy on screen', () => {
    render(<CompanyFormatConsole onClose={() => undefined} />);

    expect(screen.getByText(/지금은 등록까지 됩니다/)).toBeInTheDocument();
    expect(screen.queryByText(/endpoint|vault|adapter|backend|v1\.2|#772|raw log/i)).not.toBeInTheDocument();
    expect(screen.queryByRole('option', { name: 'test_only' })).not.toBeInTheDocument();
  });

  it('offers accounting format kinds with Korean-only option text (no internal value suffix)', () => {
    render(<CompanyFormatConsole onClose={() => undefined} />);

    expect(FORMAT_KINDS).toContain('cash_flow_monthly');
    expect(FORMAT_KIND_LABELS.cash_flow_monthly).toBe('월간 현금흐름');
    expect(screen.getByRole('option', { name: '월간 현금흐름' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: '손익 요약' })).toBeInTheDocument();
    // 괄호 안 내부값(영문 enum)은 화면에서 제거된다.
    expect(screen.queryByRole('option', { name: /\(cash_flow_monthly\)|\(pnl_summary\)|\(report\)/ })).not.toBeInTheDocument();
  });

  it('blocks submit until admin digest and template fields are valid', () => {
    render(<CompanyFormatConsole onClose={() => undefined} />);

    expect(screen.getByRole('button', { name: '양식 등록' })).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Admin ID digest'), { target: { value: DIGEST } });
    fireEvent.change(screen.getByLabelText('Admin session digest'), { target: { value: DIGEST } });
    fireEvent.change(screen.getByLabelText('양식 제목'), { target: { value: '보고서 양식' } });
    fireEvent.change(screen.getByLabelText('부서 digest'), { target: { value: DIGEST } });
    fireEvent.change(screen.getByLabelText('양식 원문'), { target: { value: RAW_TEMPLATE } });
    expect(screen.getByRole('button', { name: '양식 등록' })).toBeEnabled();
  });
});
