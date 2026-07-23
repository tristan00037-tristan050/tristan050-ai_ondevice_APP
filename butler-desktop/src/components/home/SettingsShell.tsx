import React, { useEffect, useRef } from 'react';
import { currentBuildIdentity } from '../../lib/buildIdentity';

export type SettingsAction = 'policy' | 'format' | 'fact' | 'learning' | 'accounting' | 'egress';

interface SettingsShellProps {
  onClose: () => void;
  onAction: (action: SettingsAction) => void;
  appVersion: string;
  engineVersion: string | null;
}

const GROUPS = [
  { title: '우리 회사', rows: [{ label: '처음 설정하기', action: 'accounting' as const, note: '회사와 회계 기본 정보를 등록합니다.' }] },
  { title: '정책·보안', rows: [{ label: '정책 관리', action: 'policy' as const }, { label: '외부 전송 상태', action: 'egress' as const }] },
  { title: '회사 배우기', rows: [{ label: '승인된 회사 지식', action: 'fact' as const }, { label: '폴더 학습 후보', action: 'learning' as const }, { label: '회사 양식', action: 'format' as const }] },
  { title: '데이터', rows: [{ label: '내보내기·삭제 관리', note: '준비 중' }] },
  { title: '개인화', rows: [{ label: '말투·답변 길이', note: '준비 중' }] },
  { title: '화면', rows: [{ label: '확대·테마·창 초기화', note: '준비 중' }] },
] as const;

const FOCUSABLE = 'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export function SettingsShell({ onClose, onAction, appVersion, engineVersion }: SettingsShellProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const buildIdentity = currentBuildIdentity();

  useEffect(() => {
    const dialog = dialogRef.current;
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    if (!dialog) return;
    if (typeof dialog.showModal === 'function') dialog.showModal();
    else dialog.setAttribute('open', '');
    closeRef.current?.focus();

    const trap = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== 'Tab') return;
      const focusable = Array.from(dialog.querySelectorAll<HTMLElement>(FOCUSABLE));
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
    dialog.addEventListener('keydown', trap);
    return () => {
      dialog.removeEventListener('keydown', trap);
      if (dialog.open && typeof dialog.close === 'function') dialog.close();
      opener?.focus();
    };
  }, [onClose]);

  return (
    <dialog
      ref={dialogRef}
      className="settings-shell"
      aria-labelledby="settings-title"
      onCancel={event => { event.preventDefault(); onClose(); }}
      onMouseDown={event => {
        const rect = event.currentTarget.getBoundingClientRect();
        if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) onClose();
      }}
    >
      <header>
        <div><p className="eyebrow">Butler 설정</p><h2 id="settings-title">설정</h2></div>
        <button ref={closeRef} onClick={onClose} aria-label="설정 닫기">닫기</button>
      </header>
      <div className="settings-groups">
        {GROUPS.map(group => (
          <section className="settings-group" key={group.title}>
            <h3>{group.title}</h3>
            {group.rows.map(row => (
              <div className="settings-row" key={row.label}>
                <div><strong>{row.label}</strong>{'note' in row && row.note && <span>{row.note}</span>}</div>
                {'action' in row && row.action
                  ? <button onClick={() => onAction(row.action)}>열기</button>
                  : <span className="not-ready" aria-label={`${row.label} 준비 중`}>준비 중</span>}
              </div>
            ))}
          </section>
        ))}
        <section className="settings-group">
          <h3>이 버틀러 정보</h3>
          <dl className="product-info">
            <div><dt>앱</dt><dd>{appVersion}</dd></div>
            <div><dt>빌드</dt><dd>{buildIdentity.shortCommit}</dd></div>
            <div><dt>빌드 문맥</dt><dd title={buildIdentity.contextDigest}>{buildIdentity.contextDigest.slice(0, 12)}</dd></div>
            <div><dt>채널</dt><dd>{buildIdentity.channel}</dd></div>
            <div><dt>엔진</dt><dd>{engineVersion ?? '확인되지 않음'}</dd></div>
          </dl>
        </section>
      </div>
    </dialog>
  );
}
