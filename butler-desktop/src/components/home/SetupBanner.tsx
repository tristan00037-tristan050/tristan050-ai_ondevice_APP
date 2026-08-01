import React, { useState } from 'react';
import {
  readSetupBannerDismissed,
  shouldShowSetupBanner,
  writeSetupBannerDismissed,
  type SetupUiState,
} from '../../lib/setupBanner';

type Props = Readonly<{
  setup: SetupUiState;
  onStart: () => void;
}>;

function sessionStorageOrUndefined(): Storage | undefined {
  if (typeof window === 'undefined') return undefined;
  try {
    return window.sessionStorage;
  } catch {
    return undefined;
  }
}

export function SetupBanner({ setup, onStart }: Props) {
  const [dismissed, setDismissed] = useState(
    () => readSetupBannerDismissed(sessionStorageOrUndefined()),
  );

  if (!shouldShowSetupBanner(setup, dismissed)) return null;

  const dismiss = () => {
    setDismissed(true);
    writeSetupBannerDismissed(sessionStorageOrUndefined());
    window.requestAnimationFrame(() => {
      const next = document.querySelector<HTMLElement>(
        '[data-home-card="true"]:not([disabled]), [data-testid="text-input"]',
      );
      next?.focus();
    });
  };

  return (
    <section
      className="setup-banner"
      data-testid="setup-banner"
      role="region"
      aria-label="회사 설정 시작 안내"
    >
      <div>
        <strong>회사 맞춤 설정을 마치면 Butler를 더 정확하게 사용할 수 있습니다.</strong>
        <span>설정 상태를 확인하고 필요한 항목을 이어서 입력하세요.</span>
      </div>
      <button className="setup-banner-start" type="button" onClick={onStart}>
        시작하기
      </button>
      <button
        className="setup-banner-dismiss"
        data-testid="setup-banner-dismiss"
        type="button"
        aria-label="시작하기 안내 닫기"
        onClick={dismiss}
      >
        ×
      </button>
    </section>
  );
}
