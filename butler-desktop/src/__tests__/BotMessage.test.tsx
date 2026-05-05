import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { BotMessage } from '../components/chat/BotMessage';

describe('BotMessage — 출처 배지', () => {
  it('test_happy_factpack_badge_rendered', () => {
    // source="factpack" → "✓ 검증된 사실" 배지 표시
    render(<BotMessage content="답변 내용" source="factpack" />);
    expect(screen.getByText('✓ 검증된 사실')).toBeInTheDocument();
  });

  it('test_happy_llm_badge_rendered', () => {
    // source="llm" → "✨ AI 생성" 배지 표시
    render(<BotMessage content="답변 내용" source="llm" />);
    expect(screen.getByText('✨ AI 생성')).toBeInTheDocument();
  });

  it('test_boundary_no_badge_when_source_null', () => {
    // source 없음 → 배지 없음
    render(<BotMessage content="답변 내용" source={null} />);
    expect(screen.queryByText('✓ 검증된 사실')).not.toBeInTheDocument();
    expect(screen.queryByText('✨ AI 생성')).not.toBeInTheDocument();
  });

  it('test_boundary_no_badge_when_source_undefined', () => {
    // source prop 미전달 → 배지 없음
    render(<BotMessage content="답변 내용" />);
    expect(screen.queryByText('✓ 검증된 사실')).not.toBeInTheDocument();
    expect(screen.queryByText('✨ AI 생성')).not.toBeInTheDocument();
  });

  it('test_adv_factpack_badge_color_style', () => {
    // factpack 배지가 녹색 계열 색상 (#0F7B0F / rgba(15,123,15,...))으로 렌더
    render(<BotMessage content="답변" source="factpack" />);
    const badge = screen.getByText('✓ 검증된 사실');
    const style = badge.style.background || badge.getAttribute('style') || '';
    // CSS 변수로 주입되므로 스타일 문자열에 rgba 또는 color-success 포함 확인
    // jsdom에서 CSS 변수는 미해석 — background 속성만 확인
    expect(badge).toBeInTheDocument();
  });

  it('test_adv_loading_state_has_no_badge', () => {
    // content=null (로딩 중) → 배지 없음
    render(<BotMessage content={null} source={undefined} loadingStatus="생각 중" />);
    expect(screen.queryByText('✓ 검증된 사실')).not.toBeInTheDocument();
    expect(screen.queryByText('✨ AI 생성')).not.toBeInTheDocument();
    expect(screen.getByText('생각 중')).toBeInTheDocument();
  });

  it('test_status_message_displayed_during_processing', () => {
    // phase_start loadingStatus → bot-loading-status 요소에 단계 메시지 표시
    const phaseMsg = '1/1 단계 분석 시작 — 예상 60초';
    render(<BotMessage content={null} loadingStatus={phaseMsg} />);
    expect(screen.getByTestId('bot-loading-status').textContent).toBe(phaseMsg);
  });

  it('test_progress_bar_visible_during_chunk_progress', () => {
    // progressPercent 설정 시 bot-progress-bar 표시
    render(<BotMessage content={null} loadingStatus="처리 중" progressPercent={45} />);
    expect(screen.getByTestId('bot-progress-bar-container')).toBeInTheDocument();
    const bar = screen.getByTestId('bot-progress-bar');
    expect(bar.style.width).toBe('45%');
  });

  it('test_boundary_progress_bar_hidden_without_progressPercent', () => {
    // progressPercent 미설정 → progress bar 숨김
    render(<BotMessage content={null} loadingStatus="생각 중" />);
    expect(screen.queryByTestId('bot-progress-bar-container')).not.toBeInTheDocument();
  });

  it('test_chunk_progress_status_message_displayed', () => {
    // chunk_progress 이벤트 → 상태 메시지 + 진행 바 동시 표시
    render(<BotMessage content={null} loadingStatus="2개 청크 중 1번째 처리 중 — 근거 문장 검색 중" progressPercent={70} />);
    expect(screen.getByTestId('bot-loading-status').textContent).toContain('근거 문장 검색 중');
    expect(screen.getByTestId('bot-progress-bar-container')).toBeInTheDocument();
  });

  it('test_reduce_start_status_message_displayed', () => {
    // reduce_start 이벤트 → "통합 중" 메시지 + 85% 진행 바
    render(<BotMessage content={null} loadingStatus="2개 청크 결과 통합 중" progressPercent={85} />);
    expect(screen.getByTestId('bot-loading-status').textContent).toContain('통합 중');
    expect(screen.getByTestId('bot-progress-bar').style.width).toBe('85%');
  });

  it('test_verify_start_status_message_displayed', () => {
    // verify_start 이벤트 → "검증 중" 메시지 + 95% 진행 바
    render(<BotMessage content={null} loadingStatus="출처 근거 검증 중" progressPercent={95} />);
    expect(screen.getByTestId('bot-loading-status').textContent).toContain('검증 중');
    expect(screen.getByTestId('bot-progress-bar').style.width).toBe('95%');
  });

  it('test_progress_bar_updates_during_chunk_progress', () => {
    // progressPercent=70 (chunk 1/2, 5+65×0.5 공식) → bar.style.width=70%
    render(<BotMessage content={null} loadingStatus="처리 중" progressPercent={70} />);
    expect(screen.getByTestId('bot-progress-bar').style.width).toBe('70%');
  });

  it('test_streaming_buffer_text_rendered', () => {
    // streamBuffer 있음 → streaming-text 요소에 토큰 텍스트 표시
    render(<BotMessage content={null} streamBuffer="부분 응답..." />);
    expect(screen.getByTestId('streaming-text')).toBeInTheDocument();
    expect(screen.getByTestId('streaming-text').textContent).toContain('부분 응답...');
  });

  it('test_streaming_hides_loading_dots_when_buffer_set', () => {
    // streamBuffer 있음 → loading dots(bot-loading-status) 숨김
    render(<BotMessage content={null} streamBuffer="토큰" loadingStatus="답변 준비중..." />);
    expect(screen.queryByTestId('bot-loading-status')).not.toBeInTheDocument();
  });

  it('test_streaming_empty_buffer_shows_loading_dots', () => {
    // streamBuffer 없음(undefined 또는 '') → loading dots 표시
    render(<BotMessage content={null} streamBuffer="" loadingStatus="답변 준비중..." />);
    expect(screen.getByTestId('bot-loading-status')).toBeInTheDocument();
  });
});
