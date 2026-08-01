import React, { useEffect, useRef, useState } from 'react';
import { X } from 'lucide-react';
import {
  buildAdminHeadersInput,
  isSha256Digest,
  type AdminAuthMethod,
} from '../../lib/admin_policy/contracts';
import {
  CompanyProfileError,
  registerCompanyProfile,
} from '../../lib/companyProfile';

type Props = Readonly<{
  onClose: () => void;
  onComplete: () => void;
}>;

type FormState = Readonly<{
  companyAliases: string;
  bankHolderAliases: string;
  accountNumbers: string;
  adminIdDigest: string;
  adminSessionDigest: string;
  authMethod: AdminAuthMethod;
}>;

const INITIAL_FORM: FormState = {
  companyAliases: '',
  bankHolderAliases: '',
  accountNumbers: '',
  adminIdDigest: '',
  adminSessionDigest: '',
  authMethod: 'tauri_secure_invoke',
};
const FOCUSABLE =
  'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

function runtimeValues(value: string): string[] {
  return Array.from(new Set(
    value
      .split(/[\n,]/)
      .map(item => item.trim())
      .filter(Boolean),
  ));
}

function errorMessage(error: unknown): string {
  if (error instanceof CompanyProfileError) {
    if (error.code === 'COMPANY_PROFILE_REQUEST_INVALID') {
      return '입력 항목을 다시 확인해 주세요.';
    }
    if (error.code === 'COMPANY_PROFILE_HTTP_ERROR') {
      return '관리자 확인 또는 회사정보 저장에 실패했습니다.';
    }
  }
  return '회사정보를 저장하지 못했습니다. 잠시 후 다시 시도해 주세요.';
}

export function CompanyProfileSetupModal({ onClose, onComplete }: Props) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const firstInputRef = useRef<HTMLTextAreaElement>(null);
  const [form, setForm] = useState<FormState>(INITIAL_FORM);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const companyAliases = runtimeValues(form.companyAliases);
  const bankHolderAliases = runtimeValues(form.bankHolderAliases);
  const accountNumbers = runtimeValues(form.accountNumbers);
  const canSubmit = (
    companyAliases.length > 0
    && bankHolderAliases.length > 0
    && isSha256Digest(form.adminIdDigest)
    && isSha256Digest(form.adminSessionDigest)
    && !submitting
  );

  useEffect(() => {
    const dialog = dialogRef.current;
    const opener = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
    if (!dialog) return;
    if (typeof dialog.showModal === 'function') dialog.showModal();
    else dialog.setAttribute('open', '');
    firstInputRef.current?.focus();

    const trapFocus = (event: KeyboardEvent) => {
      if (event.key !== 'Tab') return;
      const focusable = Array.from(
        dialog.querySelectorAll<HTMLElement>(FOCUSABLE),
      );
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    dialog.addEventListener('keydown', trapFocus);
    return () => {
      dialog.removeEventListener('keydown', trapFocus);
      if (dialog.open && typeof dialog.close === 'function') dialog.close();
      opener?.focus();
    };
  }, []);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      const admin = buildAdminHeadersInput({
        role: 'admin',
        adminIdDigest: form.adminIdDigest,
        adminSessionDigest: form.adminSessionDigest,
        authMethod: form.authMethod,
      });
      await registerCompanyProfile({
        own_bank_holder_aliases: bankHolderAliases,
        own_company_aliases: companyAliases,
        own_account_numbers: accountNumbers,
        own_bank_accounts: [],
      }, admin);
      onComplete();
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <dialog
      ref={dialogRef}
      className="company-profile-setup"
      data-testid="company-profile-setup-modal"
      aria-labelledby="company-profile-setup-title"
      onCancel={event => {
        event.preventDefault();
        if (!submitting) onClose();
      }}
    >
      <header>
        <div>
          <p className="eyebrow">Butler 처음 설정</p>
          <h2 id="company-profile-setup-title">회사정보 등록</h2>
        </div>
        <button
          className="icon-button"
          type="button"
          aria-label="회사정보 등록 닫기"
          title="닫기"
          disabled={submitting}
          onClick={onClose}
        >
          <X aria-hidden="true" size={18} />
        </button>
      </header>
      <form onSubmit={submit}>
        <label>
          회사명과 별칭
          <textarea
            ref={firstInputRef}
            value={form.companyAliases}
            onChange={event => setForm(current => ({
              ...current,
              companyAliases: event.target.value,
            }))}
            placeholder="회사명, 자주 쓰는 별칭"
            required
          />
        </label>
        <label>
          자사 계좌 예금주명
          <textarea
            value={form.bankHolderAliases}
            onChange={event => setForm(current => ({
              ...current,
              bankHolderAliases: event.target.value,
            }))}
            placeholder="예금주명, 통장에 표시되는 이름"
            required
          />
        </label>
        <label>
          자사 계좌번호
          <textarea
            value={form.accountNumbers}
            onChange={event => setForm(current => ({
              ...current,
              accountNumbers: event.target.value,
            }))}
            placeholder="선택 항목, 여러 개는 줄바꿈으로 구분"
          />
        </label>
        <fieldset>
          <legend>관리자 확인</legend>
          <label>
            관리자 ID 확인값
            <input
              type="password"
              autoComplete="off"
              value={form.adminIdDigest}
              onChange={event => setForm(current => ({
                ...current,
                adminIdDigest: event.target.value.trim(),
              }))}
              placeholder="sha256:"
              required
            />
          </label>
          <label>
            관리자 세션 확인값
            <input
              type="password"
              autoComplete="off"
              value={form.adminSessionDigest}
              onChange={event => setForm(current => ({
                ...current,
                adminSessionDigest: event.target.value.trim(),
              }))}
              placeholder="sha256:"
              required
            />
          </label>
          <label>
            확인 방식
            <select
              value={form.authMethod}
              onChange={event => setForm(current => ({
                ...current,
                authMethod: event.target.value as AdminAuthMethod,
              }))}
            >
              <option value="tauri_secure_invoke">기기 보안 확인</option>
              <option value="os_keychain">운영체제 키체인</option>
            </select>
          </label>
        </fieldset>
        {error && <p className="company-profile-error" role="alert">{error}</p>}
        <footer>
          <button type="button" disabled={submitting} onClick={onClose}>
            취소
          </button>
          <button className="primary-button" type="submit" disabled={!canSubmit}>
            {submitting ? '저장 중' : '등록 완료'}
          </button>
        </footer>
      </form>
    </dialog>
  );
}
