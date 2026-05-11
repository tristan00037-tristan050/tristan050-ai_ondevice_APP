vi.mock('@tauri-apps/plugin-dialog', () => ({ save: vi.fn() }));
vi.mock('@tauri-apps/plugin-fs', () => ({ writeFile: vi.fn() }));

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { DocumentTransformModal } from '../components/chat/DocumentTransformModal';

beforeEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
});

// ── Test 1: 파일 미선택 시 변환 버튼 비활성화 ──────────────────────────────

describe('DocumentTransformModal 버튼 상태', () => {
  it('test_transform_btn_disabled_when_no_files_selected', () => {
    render(<DocumentTransformModal onClose={() => {}} />);
    const btn = screen.getByRole('button', { name: '변환하기' });
    // 파일 미선택 → disabled (cursor:not-allowed + backgroundColor:#d1d5db)
    expect(btn).toHaveStyle({ cursor: 'not-allowed' });
  });
});

// ── Test 2: fetch 실패 시 재시도 메시지 출력 ──────────────────────────────

describe('DocumentTransformModal 사이드카 첫 호출 재시도', () => {
  it('test_modal_shows_retry_status_on_network_error', async () => {
    // fetch가 항상 네트워크 오류로 실패하는 경우
    vi.spyOn(global, 'fetch').mockRejectedValue(new TypeError('Load failed'));

    render(<DocumentTransformModal onClose={() => {}} />);

    // 두 파일 입력 중 첫 번째 input
    const fileInputs = document.querySelectorAll('input[type="file"]');
    const externalInput = Array.from(fileInputs).find(el =>
      (el as HTMLInputElement).getAttribute('accept')?.includes('.eml')
    ) as HTMLInputElement;
    const templateInput = Array.from(fileInputs).find(el => {
      const accept = (el as HTMLInputElement).getAttribute('accept') ?? '';
      return accept.includes('.docx') && !accept.includes('.eml');
    }) as HTMLInputElement;

    const extFile = new File(['외부 문서 내용'], 'external.txt', { type: 'text/plain' });
    const tplFile = new File(['# 양식\n\n내용'], 'template.md', { type: 'text/markdown' });

    await act(async () => {
      fireEvent.change(externalInput, { target: { files: [extFile] } });
      fireEvent.change(templateInput, { target: { files: [tplFile] } });
    });

    const btn = screen.getByRole('button', { name: '변환하기' });
    await act(async () => {
      fireEvent.click(btn);
    });

    // 재시도 메시지가 출현해야 함 (연결 재시도 중...)
    await waitFor(
      () => {
        const body = document.body.textContent ?? '';
        return body.includes('재시도') || body.includes('연결') || body.includes('오류');
      },
      { timeout: 8000 }
    );
    const bodyText = document.body.textContent ?? '';
    expect(bodyText).toMatch(/재시도|연결|오류|실패/);
  }, 15_000);

  // ── Test 3: fake timer로 재시도 딜레이 제어 → fetch 2회 호출 확인 ──────────

  it('test_fetch_called_twice_after_first_load_failed', async () => {
    vi.useFakeTimers();
    try {
      let callCount = 0;
      vi.spyOn(global, 'fetch').mockImplementation(async () => {
        callCount++;
        throw new TypeError('Load failed');
      });

      render(<DocumentTransformModal onClose={() => {}} />);

      const fileInputs = document.querySelectorAll('input[type="file"]');
      const externalInput = Array.from(fileInputs).find(el =>
        (el as HTMLInputElement).getAttribute('accept')?.includes('.eml')
      ) as HTMLInputElement;
      const templateInput = Array.from(fileInputs).find(el => {
        const accept = (el as HTMLInputElement).getAttribute('accept') ?? '';
        return accept.includes('.docx') && !accept.includes('.eml');
      }) as HTMLInputElement;

      await act(async () => {
        fireEvent.change(externalInput, { target: { files: [new File(['text'], 'ext.txt')] } });
        fireEvent.change(templateInput, { target: { files: [new File(['# h'], 'tpl.md')] } });
      });

      // 변환하기 클릭 → 첫 번째 fetch 시도 (실패) → retry delay 진입
      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: '변환하기' }));
      });

      // 재시도 딜레이(2000ms)를 넘겨 두 번째 fetch 트리거
      await act(async () => {
        await vi.advanceTimersByTimeAsync(3000);
      });

      // fetch 2회 호출 (원본 + 재시도) 확인
      expect(callCount).toBeGreaterThanOrEqual(2);
    } finally {
      vi.useRealTimers();
    }
  }, 15_000);
});
