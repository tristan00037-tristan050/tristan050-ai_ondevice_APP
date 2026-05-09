import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { EmptyState } from '../components/chat/EmptyState';

describe('EmptyState — 카드 선택/해제 동기화', () => {
  it('test_card_click_emits_mode', () => {
    // 카드 최초 클릭 → onCardSelect(mode) 호출
    const onCardSelect = vi.fn();
    render(<EmptyState onCardSelect={onCardSelect} />);
    fireEvent.click(screen.getByTestId('card-1'));
    expect(onCardSelect).toHaveBeenCalledOnce();
    expect(onCardSelect).toHaveBeenCalledWith('request_organize');
  });

  it('test_same_card_reclick_emits_null', () => {
    // 같은 카드 재클릭 → onCardSelect(null) 호출 (해제)
    const onCardSelect = vi.fn();
    render(<EmptyState onCardSelect={onCardSelect} />);
    fireEvent.click(screen.getByTestId('card-1'));
    fireEvent.click(screen.getByTestId('card-1'));
    expect(onCardSelect).toHaveBeenCalledTimes(2);
    expect(onCardSelect).toHaveBeenNthCalledWith(1, 'request_organize');
    expect(onCardSelect).toHaveBeenNthCalledWith(2, null);
  });

  it('test_different_card_click_emits_new_mode', () => {
    // 카드1 선택 후 카드5(활성) 클릭 → onCardSelect(card5_mode) 호출 (카드2,3,4,6,7,8은 비활성)
    const onCardSelect = vi.fn();
    render(<EmptyState onCardSelect={onCardSelect} />);
    fireEvent.click(screen.getByTestId('card-1'));
    fireEvent.click(screen.getByTestId('card-5'));
    expect(onCardSelect).toHaveBeenCalledTimes(2);
    expect(onCardSelect).toHaveBeenNthCalledWith(1, 'request_organize');
    expect(onCardSelect).toHaveBeenNthCalledWith(2, 'accounting_classify');
  });

  it('test_boundary_aria_pressed_reflects_active_state', () => {
    // aria-pressed 속성이 activeMode와 일치하는지 확인
    render(<EmptyState />);
    const card1 = screen.getByTestId('card-1');
    expect(card1).toHaveAttribute('aria-pressed', 'false');
    fireEvent.click(card1);
    expect(card1).toHaveAttribute('aria-pressed', 'true');
    fireEvent.click(card1);
    expect(card1).toHaveAttribute('aria-pressed', 'false');
  });

  it('test_boundary_accounting_card_shows_upload_guide', () => {
    // card-5(회계 분류) 클릭 시 bank-upload-guide 표시
    render(<EmptyState />);
    expect(screen.queryByTestId('bank-upload-guide')).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId('card-5'));
    expect(screen.getByTestId('bank-upload-guide')).toBeInTheDocument();
  });

  it('test_boundary_accounting_card_deselect_hides_guide', () => {
    // card-5 재클릭(해제) 시 bank-upload-guide 숨김
    render(<EmptyState />);
    fireEvent.click(screen.getByTestId('card-5'));
    expect(screen.getByTestId('bank-upload-guide')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('card-5'));
    expect(screen.queryByTestId('bank-upload-guide')).not.toBeInTheDocument();
  });
});
