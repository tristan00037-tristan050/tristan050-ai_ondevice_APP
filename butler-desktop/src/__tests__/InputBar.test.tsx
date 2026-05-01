import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { InputBar } from '../components/InputBar';

describe('InputBar', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('test_happy_text_input_and_submit', () => {
    const onSubmit = vi.fn();
    render(<InputBar onSubmit={onSubmit} />);
    const textarea = screen.getByTestId('text-input');
    fireEvent.change(textarea, { target: { value: '회의록 요약해줘' } });
    expect(textarea).toHaveValue('회의록 요약해줘');
    fireEvent.click(screen.getByTestId('send-btn'));
    expect(onSubmit).toHaveBeenCalledWith('회의록 요약해줘', []);
  });

  it('test_happy_file_drop_triggers_precheck', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      json: () => Promise.resolve({ grade: 'S' }),
    });
    vi.stubGlobal('fetch', mockFetch);

    const onSubmit = vi.fn();
    render(<InputBar onSubmit={onSubmit} precheckUrl="/api/precheck" />);

    const file = new File(['content'], 'report.pdf', { type: 'application/pdf' });
    const dropZone = screen.getByTestId('drop-zone');
    fireEvent.drop(dropZone, { dataTransfer: { files: [file] } });

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith('/api/precheck', expect.objectContaining({ method: 'POST' }));
    });

    vi.unstubAllGlobals();
  });

  it('test_boundary_xl_file_shows_team_hub_guide', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      json: () => Promise.resolve({ grade: 'XL' }),
    });
    vi.stubGlobal('fetch', mockFetch);

    render(<InputBar onSubmit={vi.fn()} precheckUrl="/api/precheck" />);
    const file = new File(['x'.repeat(100)], 'bigfile.pdf', { type: 'application/pdf' });
    fireEvent.drop(screen.getByTestId('drop-zone'), { dataTransfer: { files: [file] } });

    await waitFor(() => {
      expect(screen.getByTestId('team-hub-guide')).toBeInTheDocument();
    });

    vi.unstubAllGlobals();
  });

  it('test_adv_voice_input_permission_handling', async () => {
    const mockVoice = vi.fn().mockResolvedValue('음성으로 입력된 텍스트');
    render(<InputBar onSubmit={vi.fn()} invokeVoice={mockVoice} />);
    fireEvent.click(screen.getByTestId('voice-btn'));
    await waitFor(() => expect(mockVoice).toHaveBeenCalled());
    await waitFor(() => {
      expect(screen.getByTestId('text-input')).toHaveValue('음성으로 입력된 텍스트');
    });
  });

  it('test_adv_max_4000_chars_enforced', () => {
    render(<InputBar onSubmit={vi.fn()} maxLength={4000} />);
    const textarea = screen.getByTestId('text-input');
    expect(textarea).toHaveAttribute('maxLength', '4000');
    const longText = 'A'.repeat(5000);
    fireEvent.change(textarea, { target: { value: longText } });
    expect((textarea as HTMLTextAreaElement).value).toHaveLength(4000);
  });
});
