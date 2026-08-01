import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../lib/companyProfile', async importOriginal => {
  const original = await importOriginal<typeof import('../../lib/companyProfile')>();
  return { ...original, registerCompanyProfile: vi.fn() };
});

import { registerCompanyProfile } from '../../lib/companyProfile';
import { CompanyProfileSetupModal } from './CompanyProfileSetupModal';

const mockedRegister = vi.mocked(registerCompanyProfile);
const DIGEST = `sha256:${'a'.repeat(64)}` as const;

describe('CompanyProfileSetupModal', () => {
  beforeEach(() => mockedRegister.mockReset());

  it('registers canonical company information and completes setup', async () => {
    mockedRegister.mockResolvedValueOnce({
      schemaVersion: 'company_profile.register.response.v1',
      profileId: 'profile-01',
      profileDigest: DIGEST,
      displayHints: {},
      rawTextLogged: false,
      plaintextPersisted: false,
      externalSendZero: true,
      a4RegistryReady: false,
      a4RegistryDigest: null,
    });
    const onComplete = vi.fn();
    render(<CompanyProfileSetupModal onClose={vi.fn()} onComplete={onComplete} />);

    fireEvent.change(screen.getByLabelText('회사명과 별칭'), {
      target: { value: '주식회사 버틀러\n버틀러' },
    });
    fireEvent.change(screen.getByLabelText('자사 계좌 예금주명'), {
      target: { value: '주식회사 버틀러' },
    });
    fireEvent.change(screen.getByLabelText('자사 계좌번호'), {
      target: { value: '123-456' },
    });
    fireEvent.change(screen.getByLabelText('관리자 ID 확인값'), {
      target: { value: DIGEST },
    });
    fireEvent.change(screen.getByLabelText('관리자 세션 확인값'), {
      target: { value: DIGEST },
    });
    fireEvent.click(screen.getByRole('button', { name: '등록 완료' }));

    await waitFor(() => expect(mockedRegister).toHaveBeenCalledWith(
      {
        own_bank_holder_aliases: ['주식회사 버틀러'],
        own_company_aliases: ['주식회사 버틀러', '버틀러'],
        own_account_numbers: ['123-456'],
        own_bank_accounts: [],
      },
      {
        role: 'admin',
        admin_id_digest: DIGEST,
        admin_session_digest: DIGEST,
        auth_method: 'tauri_secure_invoke',
      },
    ));
    expect(onComplete).toHaveBeenCalledOnce();
  });
});
