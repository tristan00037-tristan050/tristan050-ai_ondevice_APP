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

describe('Box3DraftModal unsupported-claim labels', () => {
  it('shows a needs-review banner and highlights labeled draft lines', async () => {
    vi.mocked(createBox3Draft).mockResolvedValueOnce({
      status: 'real_candidate',
      draft_text: '제목: 납품 보고\n[근거 확인 필요] 핵심 내용: 납품 일정은 2026년 6월 20일입니다.',
      fail_class: 'NEEDS_REVIEW_UNSUPPORTED_CLAIM',
      needs_review: true,
      review_reason_code: 'NEEDS_REVIEW_UNSUPPORTED_CLAIM',
      unsupported_claim_count: 1,
      annotated_claim_count: 1,
      label_coverage_ok: true,
      raw_doc_logged: false,
    });

    render(<Box3DraftModal onClose={() => {}} />);
    fireEvent.change(screen.getByTestId('box3-reference-input'), { target: { value: '납품 일정은 2026년 6월 10일입니다.' } });
    fireEvent.change(screen.getByTestId('box3-request-input'), { target: { value: '납품 보고 초안 작성' } });
    fireEvent.click(screen.getByTestId('box3-submit-btn'));

    await waitFor(() => expect(screen.getByTestId('box3-needs-review-banner')).toBeInTheDocument());
    expect(screen.getByTestId('box3-needs-review-banner')).toHaveTextContent(
      '근거가 확인되지 않은 문장이 1건 있습니다. [근거 확인 필요] 표시가 있는 줄은 사람이 반드시 검토해야 합니다.',
    );
    expect(screen.getByTestId('box3-unsupported-label-line')).toHaveTextContent('[근거 확인 필요]');
    expect(screen.queryByText('라벨 제거')).toBeNull();
  });
});
