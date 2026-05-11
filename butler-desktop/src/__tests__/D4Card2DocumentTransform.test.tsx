vi.mock('@tauri-apps/plugin-dialog', () => ({ save: vi.fn() }));
vi.mock('@tauri-apps/plugin-fs', () => ({ writeFile: vi.fn() }));

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { App } from '../App';
import { DocumentTransformModal } from '../components/chat/DocumentTransformModal';

beforeEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
  vi.spyOn(global, 'fetch').mockResolvedValue(
    new Response('{"status":"ok"}', { status: 200 })
  );
});

// ── Test 1: Card 2 클릭 → DocumentTransformModal 표시 ────────────────────────

describe('Card 2 format_convert routing', () => {
  it('test_document_transform_modal_opens_when_card2_clicked', async () => {
    render(<App />);

    // wait for sidecar ready (health returns ok immediately in mock)
    const card2 = await screen.findByTestId('card-2');
    fireEvent.click(card2);

    const modal = await screen.findByTestId('document-transform-modal');
    expect(modal).toBeInTheDocument();
  });
});

// ── Test 2: 모달 헤더 ArrowRightLeft SVG 아이콘 ───────────────────────────────

describe('DocumentTransformModal header icon', () => {
  it('test_modal_header_has_arrowrightleft_svg_not_emoji', () => {
    render(<DocumentTransformModal onClose={() => {}} />);
    const heading = screen.getByRole('heading', { level: 2 });
    // 이모지 사용 금지 (Lucide 아이콘 의무) — §8.4
    expect(heading.textContent).not.toMatch(/[\u{1F300}-\u{1F9FF}]/u);
    // ArrowRightLeft SVG가 헤더 컨테이너에 존재해야 함
    const headerContainer = heading.closest('[style]') ?? heading.parentElement;
    const svg = headerContainer?.querySelector('svg') ?? document.querySelector('[data-testid="document-transform-modal"] svg');
    expect(svg).toBeTruthy();
  });
});

// ── Test 3: 두 개의 파일 입력 필드 존재 ────────────────────────────────────

describe('DocumentTransformModal file inputs', () => {
  it('test_modal_has_two_file_inputs', () => {
    render(<DocumentTransformModal onClose={() => {}} />);
    const fileInputs = document.querySelectorAll('input[type="file"]');
    expect(fileInputs.length).toBeGreaterThanOrEqual(2);
  });

  // ── Test 4: 외부 문서 input accept 형식 ──────────────────────────────────

  it('test_external_file_input_accepts_correct_formats', () => {
    render(<DocumentTransformModal onClose={() => {}} />);
    const fileInputs = Array.from(document.querySelectorAll('input[type="file"]'));
    const externalInput = fileInputs.find((el) => {
      const accept = (el as HTMLInputElement).getAttribute('accept') ?? '';
      return accept.includes('.pdf') && accept.includes('.eml');
    }) as HTMLInputElement | undefined;
    expect(externalInput).toBeTruthy();
    const accept = externalInput!.getAttribute('accept') ?? '';
    expect(accept).toContain('.docx');
    expect(accept).toContain('.pdf');
    expect(accept).toContain('.txt');
    expect(accept).toContain('.md');
    expect(accept).toContain('.eml');
  });

  // ── Test 5: 양식 파일 input accept .docx .md만 ───────────────────────────

  it('test_template_file_input_accepts_docx_and_md_only', () => {
    render(<DocumentTransformModal onClose={() => {}} />);
    const fileInputs = Array.from(document.querySelectorAll('input[type="file"]'));
    const templateInput = fileInputs.find((el) => {
      const accept = (el as HTMLInputElement).getAttribute('accept') ?? '';
      return accept.includes('.docx') && !accept.includes('.pdf') && !accept.includes('.eml');
    }) as HTMLInputElement | undefined;
    expect(templateInput).toBeTruthy();
    const accept = templateInput!.getAttribute('accept') ?? '';
    expect(accept).toContain('.docx');
    expect(accept).toContain('.md');
    expect(accept).not.toContain('.pdf');
    expect(accept).not.toContain('.eml');
  });
});
