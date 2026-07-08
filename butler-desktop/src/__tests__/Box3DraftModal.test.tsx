import React from 'react';
import { describe, expect, it } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { Box3DraftModal } from '../components/v1_1/Box3DraftModal';

describe('Box3DraftModal', () => {
  it('renders dedicated Box3 modal', () => {
    render(<Box3DraftModal onClose={() => {}} />);
    expect(screen.getByTestId('box3-draft-modal')).toBeTruthy();
    expect(screen.getByText('기존 문서 기반 새 초안')).toBeTruthy();
  });

  // 수용게이트 ④ + 3-5: getByLabelText 가 실제 textarea 를 가리킨다(라벨-입력 연결).
  it('links labels to the actual textareas', () => {
    render(<Box3DraftModal onClose={() => {}} />);
    expect(screen.getByLabelText('과거 참고 문서')).toBe(screen.getByTestId('box3-reference-input'));
    expect(screen.getByLabelText('새 상황·요구사항')).toBe(screen.getByTestId('box3-request-input'));
    expect(screen.getByTestId('box3-reference-input').tagName).toBe('TEXTAREA');
    expect(screen.getByTestId('box3-request-input').tagName).toBe('TEXTAREA');
  });

  // 수용게이트 ① + 결함 A/B: 네이티브 Choose Files 미노출, 커스텀 '파일에서 불러오기' 버튼 렌더.
  it('hides the native file input and renders a custom load button', () => {
    render(<Box3DraftModal onClose={() => {}} />);
    const loadBtn = screen.getByTestId('box3-reference-file-load-btn');
    expect(loadBtn.tagName).toBe('BUTTON');
    expect(loadBtn.textContent).toContain('파일에서 불러오기');

    const fileInput = screen.getByLabelText('과거 문서 파일') as HTMLInputElement;
    expect(fileInput.type).toBe('file');
    // 시각적 숨김(#842 패턴): tabIndex -1 + width 1px + absolute.
    expect(fileInput.getAttribute('tabindex')).toBe('-1');
    expect(fileInput.style.position).toBe('absolute');
    expect(fileInput.style.width).toBe('1px');
    // '텍스트 파일 불러오기' 별도 항목은 제거되었다.
    expect(screen.queryByText('텍스트 파일 불러오기')).toBeNull();
  });

  // 수용게이트 ③ + 결함 C: 두 입력란에 설명 문구·예시 placeholder 표시.
  it('shows guidance descriptions and example placeholders', () => {
    render(<Box3DraftModal onClose={() => {}} />);
    expect(
      screen.getByText('새 초안의 바탕이 될 기존 문서(계획서·공문·보고서 등)의 내용입니다. 직접 붙여넣거나 파일에서 불러오세요.'),
    ).toBeInTheDocument();
    expect(screen.getByText('어떤 문서를 만들지와 반영할 변경사항을 적어주세요.')).toBeInTheDocument();
    expect(
      screen.getByPlaceholderText('예: 작년 사업계획서, 지난달 공문 등 참고할 문서 내용을 붙여넣으세요.'),
    ).toBeInTheDocument();
    expect(
      screen.getByPlaceholderText('예: 첨부한 문서를 기반으로 2026년 사업계획서 초안을 구성해줘'),
    ).toBeInTheDocument();
  });

  // 수용게이트 ② + ⑤: 파일 선택 시 '과거 참고 문서' textarea 가 채워지고, 붙여넣기 입력 경로도 유지.
  it('fills the reference textarea from a selected file and preserves manual paste', async () => {
    render(<Box3DraftModal onClose={() => {}} />);
    const textarea = screen.getByTestId('box3-reference-input') as HTMLTextAreaElement;

    // 붙여넣기(수동 입력) 경로 회귀.
    fireEvent.change(textarea, { target: { value: '직접 붙여넣은 참고 문서' } });
    expect(textarea).toHaveValue('직접 붙여넣은 참고 문서');

    // 채움형: 파일 선택 → textarea 채움.
    await act(async () => {
      fireEvent.change(screen.getByTestId('box3-reference-file-input'), {
        target: { files: [new File(['작년 사업계획서 본문'], 'plan-2025.txt', { type: 'text/plain' })] },
      });
    });
    await waitFor(() => expect(textarea).toHaveValue('작년 사업계획서 본문'));

    // 채움 후 수동 수정도 가능.
    fireEvent.change(textarea, { target: { value: '파일 로드 후 수동 수정' } });
    expect(textarea).toHaveValue('파일 로드 후 수동 수정');
  });
});
