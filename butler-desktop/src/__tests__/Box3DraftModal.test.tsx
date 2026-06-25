import React from 'react';
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Box3DraftModal } from '../components/v1_1/Box3DraftModal';

describe('Box3DraftModal', () => {
  it('renders dedicated Box3 modal', () => {
    render(<Box3DraftModal onClose={() => {}} />);
    expect(screen.getByTestId('box3-draft-modal')).toBeTruthy();
    expect(screen.getByText('기존 문서 기반 새 초안')).toBeTruthy();
    expect(screen.getByLabelText('과거 참고 문서')).toBeTruthy();
    expect(screen.getByLabelText('새 상황')).toBeTruthy();
  });
});
