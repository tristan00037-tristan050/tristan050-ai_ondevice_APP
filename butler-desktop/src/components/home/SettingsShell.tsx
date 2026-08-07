import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { currentBuildIdentity } from '../../lib/buildIdentity';
import {
  fetchLearningCapabilitySnapshot,
  selectLearningRows,
  unavailableLearningCapability,
  type LearningCapabilitySnapshot,
} from '../../lib/learningCapability';

export type SettingsAction = 'profile' | 'policy' | 'format' | 'fact' | 'learning' | 'helper1' | 'accounting' | 'egress';

interface SettingsShellProps {
  onClose: () => void;
  onAction: (action: SettingsAction) => void;
  appVersion: string;
  engineVersion: string | null;
  learningCapability?: LearningCapabilitySnapshot | null;
}

const GROUPS = [
  { title: '우리 회사', rows: [{ label: '처음 설정하기', action: 'profile' as const, note: '회사와 회계 기본 정보를 등록합니다.' }] },
  { title: '정책·보안', rows: [{ label: '정책 관리', action: 'policy' as const }, { label: '외부 전송 상태', action: 'egress' as const }] },
  { title: '데이터', rows: [{ label: '내보내기·삭제 관리', note: '준비 중' }] },
  { title: '개인화', rows: [{ label: '말투·답변 길이', note: '준비 중' }] },
  { title: '화면', rows: [{ label: '확대·테마·창 초기화', note: '준비 중' }] },
] as const;

const FOCUSABLE = 'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export function SettingsShell({
  onClose,
  onAction,
  appVersion,
  engineVersion,
  learningCapability,
}: SettingsShellProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const learningRequestEpoch = useRef(0);
  const learningController = useRef<AbortController | null>(null);
  const buildIdentity = currentBuildIdentity();
  const [liveLearningCapability, setLiveLearningCapability] = useState(
    learningCapability ?? unavailableLearningCapability,
  );
  const learningRows = useMemo(
    () => selectLearningRows(liveLearningCapability),
    [liveLearningCapability],
  );

  const refreshLearningCapability = useCallback(async () => {
    if (learningCapability !== undefined) {
      setLiveLearningCapability(
        learningCapability ?? unavailableLearningCapability,
      );
      return;
    }
    const epoch = ++learningRequestEpoch.current;
    learningController.current?.abort();
    const controller = new AbortController();
    learningController.current = controller;
    // A prior success is not evidence for the new request. Remove it before
    // I/O so a transport failure cannot leave a stale green state behind.
    setLiveLearningCapability(unavailableLearningCapability);
    const snapshot = await fetchLearningCapabilitySnapshot(controller.signal);
    if (
      epoch === learningRequestEpoch.current
      && !controller.signal.aborted
    ) {
      setLiveLearningCapability(snapshot);
    }
  }, [learningCapability]);

  useEffect(() => {
    void refreshLearningCapability();
    return () => {
      learningRequestEpoch.current += 1;
      learningController.current?.abort();
    };
  }, [refreshLearningCapability]);

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
                  ? <button aria-label={`${row.label} 열기`} onClick={() => onAction(row.action)}>열기</button>
                  : <span className="not-ready" aria-label={`${row.label} 준비 중`}>준비 중</span>}
              </div>
            ))}
          </section>
        ))}
        <section
          className="settings-group"
          data-testid="company-learning-settings"
          aria-labelledby="company-learning-title"
        >
          <div className="settings-group-heading">
            <h3 id="company-learning-title">회사 배우기</h3>
            <button
              type="button"
              data-testid="learning-capability-refresh"
              onClick={() => { void refreshLearningCapability(); }}
              aria-label="회사 배우기 상태 다시 확인"
            >
              다시 확인
            </button>
          </div>
          <ul className="settings-row-list">
            {learningRows.map(row => (
              <li
                className="settings-row"
                key={row.id}
                data-testid={`learning-row-${row.id}`}
                aria-labelledby={`${row.id}-label`}
                aria-describedby={`${row.id}-status`}
              >
                <div>
                  <strong id={`${row.id}-label`}>{row.label}</strong>
                  <span id={`${row.id}-status`}>{row.statusText}</span>
                </div>
                <button
                  aria-label={`${row.label} 열기`}
                  onClick={() => onAction(row.action)}
                >
                  열기
                </button>
              </li>
            ))}
            <li
              className="settings-row"
              data-testid="learning-row-helper1"
            >
              <div>
                <strong>도우미1 회사 문서</strong>
                <span>검증된 로컬 자산이 있을 때만 사용</span>
              </div>
              <button
                aria-label="도우미1 회사 문서 열기"
                onClick={() => onAction('helper1')}
              >
                열기
              </button>
            </li>
          </ul>
        </section>
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
