import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { HomeScreen } from '../components/HomeScreen';

describe('HomeScreen', () => {
  it('test_happy_renders_six_cards', () => {
    render(<HomeScreen />);
    for (let i = 1; i <= 6; i++) {
      expect(screen.getByTestId(`card-${i}`)).toBeInTheDocument();
    }
    expect(screen.getAllByRole('button').filter(b => b.dataset.testid?.startsWith('card-'))).toHaveLength(6);
  });

  it('test_happy_card_click_activates_mode', () => {
    const onCardSelect = vi.fn();
    render(<HomeScreen onCardSelect={onCardSelect} />);
    const card1 = screen.getByTestId('card-1');
    expect(card1).toHaveAttribute('aria-pressed', 'false');
    fireEvent.click(card1);
    expect(card1).toHaveAttribute('aria-pressed', 'true');
    expect(onCardSelect).toHaveBeenCalledWith(1);
  });

  it('test_boundary_no_card_selected_shows_free_input', () => {
    render(<HomeScreen />);
    expect(screen.getByTestId('free-input-placeholder')).toBeInTheDocument();
    expect(screen.getByTestId('free-input-placeholder').textContent).toMatch(/무엇을 도와드릴까요/);
  });

  it('test_adv_card_5_shows_bank_upload_guide', () => {
    render(<HomeScreen />);
    expect(screen.queryByTestId('bank-upload-guide')).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId('card-5'));
    expect(screen.getByTestId('bank-upload-guide')).toBeInTheDocument();
    expect(screen.getByTestId('bank-upload-guide').textContent).toMatch(/통장|거래내역|첨부/);
  });

  it('test_adv_keyboard_navigation_works', () => {
    render(<HomeScreen />);
    const card2 = screen.getByTestId('card-2');
    expect(card2).toHaveAttribute('tabIndex', '0');
    expect(card2).toHaveAttribute('aria-pressed', 'false');
    fireEvent.keyDown(card2, { key: 'Enter' });
    expect(card2).toHaveAttribute('aria-pressed', 'true');
    fireEvent.keyDown(card2, { key: ' ' });
    expect(card2).toHaveAttribute('aria-pressed', 'false');
  });
});
