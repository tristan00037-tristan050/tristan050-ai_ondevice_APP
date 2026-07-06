import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

async function renderCardGridWithFlag(value?: string) {
  vi.resetModules();
  vi.unstubAllEnvs();
  if (value !== undefined) {
    vi.stubEnv('VITE_BUTLER_BOX4_DOCUMENT_REVIEW', value);
  }
  const { CardGrid } = await import('../components/v1_1/CardGrid');
  const onCardSelect = vi.fn();
  render(<CardGrid onCardSelect={onCardSelect} />);
  return { onCardSelect };
}

afterEach(() => {
  vi.unstubAllEnvs();
});

describe('Box4 document review feature flag', () => {
  it('keeps card 4 disabled when the build flag is missing', async () => {
    const { onCardSelect } = await renderCardGridWithFlag();
    const card4 = screen.getByTestId('card-4');
    expect(card4).toBeDisabled();
    fireEvent.click(card4);
    expect(onCardSelect).not.toHaveBeenCalled();
  });

  it('enables card 4 only when VITE_BUTLER_BOX4_DOCUMENT_REVIEW is 1', async () => {
    const { onCardSelect } = await renderCardGridWithFlag('1');
    const card4 = screen.getByTestId('card-4');
    expect(card4).not.toBeDisabled();
    fireEvent.click(card4);
    expect(onCardSelect).toHaveBeenCalledWith('document_review');
  });

  it('does not enable card 4 for non-1 flag values', async () => {
    await renderCardGridWithFlag('0');
    expect(screen.getByTestId('card-4')).toBeDisabled();
  });

  it('keeps cards 7 and 8 disabled when card 4 is enabled', async () => {
    await renderCardGridWithFlag('1');
    expect(screen.getByTestId('card-7')).toBeDisabled();
    expect(screen.getByTestId('card-8')).toBeDisabled();
  });
});
