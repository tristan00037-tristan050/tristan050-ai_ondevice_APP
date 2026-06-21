import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { AdminPolicyConsole } from '../components/v1_1/AdminPolicyConsole';
import { ADMIN_POLICY_ENDPOINTS, ADMIN_POLICY_SIDECAR_ORIGIN, assertLocalAdminPolicyUrl } from '../lib/admin_policy/contracts';

const DIGEST = 'sha256:' + 'a'.repeat(64);

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('AdminPolicyConsole v1.2', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('posts to the measured #772 company-policy endpoint with X-Admin headers only', async () => {
    const fetcher = vi.spyOn(global, 'fetch').mockResolvedValue(
      jsonResponse({
        schema_version: 'admin.company_policy_register.response.v1',
        policy_digest: DIGEST,
        audit_ref: DIGEST,
        admin_rbac_verified: true,
        raw_saved_zero: true,
        raw_text_logged: false,
      }),
    );

    render(<AdminPolicyConsole onClose={() => undefined} />);

    fireEvent.change(screen.getByLabelText('Admin ID digest'), { target: { value: DIGEST } });
    fireEvent.change(screen.getByLabelText('Admin session digest'), { target: { value: DIGEST } });
    fireEvent.change(screen.getByLabelText('부서 digest'), { target: { value: DIGEST } });
    fireEvent.click(screen.getByRole('button', { name: '정책 등록' }));

    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));
    const [url, init] = fetcher.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${ADMIN_POLICY_SIDECAR_ORIGIN}${ADMIN_POLICY_ENDPOINTS.registerPolicy}`);
    expect((init.headers as Record<string, string>)['X-Admin-Role']).toBe('admin');
    expect((init.headers as Record<string, string>)['X-Admin-Id-Digest']).toBe(DIGEST);
    expect((init.headers as Record<string, string>)['Authorization']).toBeUndefined();
    expect(String(init.body)).toContain('"masking_engine_verified":false');
    expect(String(init.body)).not.toContain('external_send_rules');
    const success = await screen.findByTestId('admin-policy-success');
    expect(success).toHaveTextContent('회사 보안 규칙 등록 완료');
    expect(success).not.toHaveTextContent(DIGEST);
    expect(success).not.toHaveTextContent(/sha256:|policy_digest|audit_ref/i);
  });

  it('keeps external_send_rules read-only because #772 POST payload does not support editing', () => {
    render(<AdminPolicyConsole onClose={() => undefined} />);

    expect(screen.getByLabelText('restricted external send')).toHaveValue('차단');
    expect(screen.getByLabelText('confidential external send')).toHaveValue('차단');
    expect(screen.getByLabelText('internal external send')).toHaveValue('검토 필요');
    expect(screen.getByLabelText('public external send')).toHaveValue('허용');
    expect(screen.getByText(/외부 전송 기준은 현재 기본값으로 적용됩니다/)).toBeInTheDocument();
  });

  it('shows only easy Korean labels: no developer notes, digests, or English enums', () => {
    render(<AdminPolicyConsole onClose={() => undefined} />);

    // 개발자 메모/내부 코드가 화면 텍스트로 보이지 않는다.
    expect(screen.queryByText(/#772|SSOT|capability token|policy_digest|audit_ref|sha256:/i)).not.toBeInTheDocument();
    // 상태/등급/처리 방법 옵션은 한국어로 보인다.
    expect(screen.getByRole('option', { name: '사용 중' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: '매우 민감' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: '검토 필요' })).toBeInTheDocument();
    // 영어 상태 enum 은 화면 텍스트로 보이지 않는다(option value 속성은 제외).
    expect(screen.queryByText(/^ACTIVE$|^DRAFT$|^DEPRECATED$/)).not.toBeInTheDocument();
    // 운영 화면 선택지에서 test_only 는 제거된다(타입/계약은 유지).
    expect(screen.queryByRole('option', { name: 'test_only' })).not.toBeInTheDocument();
  });

  it('shows admin permission error on backend AdminAuthError without retrying', async () => {
    const fetcher = vi.spyOn(global, 'fetch').mockResolvedValue(
      jsonResponse({ detail: { fail_class: 'ADMIN_RBAC_DENIED', message: 'admin role required' } }, 403),
    );

    render(<AdminPolicyConsole onClose={() => undefined} />);

    fireEvent.change(screen.getByLabelText('Admin ID digest'), { target: { value: DIGEST } });
    fireEvent.change(screen.getByLabelText('Admin session digest'), { target: { value: DIGEST } });
    fireEvent.change(screen.getByLabelText('부서 digest'), { target: { value: DIGEST } });
    fireEvent.click(screen.getByRole('button', { name: '정책 등록' }));

    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));
    expect(await screen.findByRole('alert')).toHaveTextContent('관리자 권한이 필요합니다');
  });

  it('rejects non-local admin policy URLs in the contract guard', () => {
    expect(() => assertLocalAdminPolicyUrl('http://localhost:8765/v1/admin/company-policy')).toThrow('BLOCK_NON_LOCAL_ADMIN_POLICY_URL');
    expect(() => assertLocalAdminPolicyUrl('https://example.invalid/v1/admin/company-policy')).toThrow('BLOCK_NON_LOCAL_ADMIN_POLICY_URL');
  });
});
