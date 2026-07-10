import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

vi.mock('../lib/box3/box3DraftClient', async () => {
  const actual = await vi.importActual<typeof import('../lib/box3/box3DraftClient')>('../lib/box3/box3DraftClient');
  return {
    ...actual,
    createBox3Draft: vi.fn(),
  };
});

import { Box3DraftModal } from '../components/v1_1/Box3DraftModal';
import { createBox3Draft } from '../lib/box3/box3DraftClient';

describe('Box3DraftModal no-draft blocked banner', () => {
  it('surfaces status/fail_class/terminal_stage by default and before the citation list when no draft', async () => {
    vi.mocked(createBox3Draft).mockResolvedValueOnce({
      status: 'BLOCKED',
      draft_text: null,
      fail_class: 'BLOCK_NO_FACTUAL_CLAIMS',
      terminal_stage: 'helper4_grounding',
      needs_review: false,
      citations: [{ evidence_id: '근거1', source_digest: 'sha256:abc' }],
      raw_doc_logged: false,
    });

    render(<Box3DraftModal onClose={() => {}} />);
    fireEvent.change(screen.getByTestId('box3-reference-input'), { target: { value: '참고 문서 내용' } });
    fireEvent.change(screen.getByTestId('box3-request-input'), { target: { value: '초안 작성' } });
    fireEvent.click(screen.getByTestId('box3-submit-btn'));

    // 차단 배너가 접힌 details 가 아니라 기본 노출로 나타난다.
    await waitFor(() => expect(screen.getByTestId('box3-blocked-banner')).toBeInTheDocument());
    expect(screen.getByTestId('box3-blocked-banner')).toHaveTextContent('초안 생성이 차단되었습니다');
    expect(screen.getByTestId('box3-blocked-status')).toHaveTextContent('BLOCKED');
    expect(screen.getByTestId('box3-blocked-fail-class')).toHaveTextContent('BLOCK_NO_FACTUAL_CLAIMS');
    expect(screen.getByTestId('box3-blocked-terminal-stage')).toHaveTextContent('helper4_grounding');

    // 배너가 citation 목록(근거)보다 먼저 나온다.
    const banner = screen.getByTestId('box3-blocked-banner');
    const citationHeading = screen.getByText('근거');
    expect(banner.compareDocumentPosition(citationHeading) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('does not render the blocked banner when a draft is present', async () => {
    vi.mocked(createBox3Draft).mockResolvedValueOnce({
      status: 'real_candidate',
      draft_text: '제목: 요약\n핵심내용: 근거 범위에서 확인합니다. (근거1)',
      fail_class: null,
      needs_review: false,
      raw_doc_logged: false,
    });

    render(<Box3DraftModal onClose={() => {}} />);
    fireEvent.change(screen.getByTestId('box3-reference-input'), { target: { value: '참고 문서 내용' } });
    fireEvent.change(screen.getByTestId('box3-request-input'), { target: { value: '초안 작성' } });
    fireEvent.click(screen.getByTestId('box3-submit-btn'));

    await waitFor(() => expect(screen.getByTestId('box3-result')).toBeInTheDocument());
    expect(screen.queryByTestId('box3-blocked-banner')).toBeNull();
  });
});
