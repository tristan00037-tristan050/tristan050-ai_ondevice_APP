import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

async function renderCardGridWithFlag(value?: string) {
  vi.resetModules();
  vi.unstubAllEnvs();
  if (value !== undefined) {
    vi.stubEnv('VITE_BOX6_FORM_FILL_ENABLED', value);
  }
  const { CardGrid } = await import('./CardGrid');
  const onCardSelect = vi.fn();
  render(<CardGrid onCardSelect={onCardSelect} />);
  return { onCardSelect };
}

afterEach(() => {
  vi.unstubAllEnvs();
});

describe('Box6 form fill feature flag', () => {
  it('keeps card 6 disabled when the build flag is missing', async () => {
    const { onCardSelect } = await renderCardGridWithFlag();

    const card6 = screen.getByTestId('card-6');
    expect(card6).toBeDisabled();

    fireEvent.click(card6);
    expect(onCardSelect).not.toHaveBeenCalled();
  });

  it('enables card 6 only when VITE_BOX6_FORM_FILL_ENABLED is 1', async () => {
    const { onCardSelect } = await renderCardGridWithFlag('1');

    const card6 = screen.getByTestId('card-6');
    expect(card6).not.toBeDisabled();

    fireEvent.click(card6);
    expect(onCardSelect).toHaveBeenCalledWith('form_fill');
  });

  it('does not enable card 6 for non-1 flag values', async () => {
    await renderCardGridWithFlag('0');
    expect(screen.getByTestId('card-6')).toBeDisabled();
  });

  it('keeps cards 7 and 8 disabled even when card 6 is enabled', async () => {
    await renderCardGridWithFlag('1');

    expect(screen.getByTestId('card-7')).toBeDisabled();
    expect(screen.getByTestId('card-8')).toBeDisabled();
  });
});
