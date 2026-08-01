export type CanonicalSetupState = Readonly<{
  status: 'loading' | 'incomplete' | 'complete';
}>;

export type SetupUiState =
  | Readonly<{ kind: 'resolving' }>
  | Readonly<{ kind: 'incomplete' }>
  | Readonly<{ kind: 'complete' }>
  | Readonly<{ kind: 'unavailable'; reason: 'canonical-signal-missing' }>;

export const SETUP_BANNER_DISMISSED_KEY =
  'butler.firstscreen.setup-banner.dismissed.v1';

export function toSetupUiState(
  source: CanonicalSetupState | undefined,
): SetupUiState {
  if (source === undefined) {
    return { kind: 'unavailable', reason: 'canonical-signal-missing' };
  }
  if (source.status === 'loading') return { kind: 'resolving' };
  if (source.status === 'complete') return { kind: 'complete' };
  return { kind: 'incomplete' };
}

export function shouldShowSetupBanner(
  setup: SetupUiState,
  dismissedForSession: boolean,
): boolean {
  if (dismissedForSession) return false;
  return setup.kind === 'incomplete' || setup.kind === 'unavailable';
}

export function readSetupBannerDismissed(
  storage: Pick<Storage, 'getItem'> | undefined,
): boolean {
  if (!storage) return false;
  try {
    return storage.getItem(SETUP_BANNER_DISMISSED_KEY) === '1';
  } catch {
    return false;
  }
}

export function writeSetupBannerDismissed(
  storage: Pick<Storage, 'setItem'> | undefined,
): void {
  if (!storage) return;
  try {
    storage.setItem(SETUP_BANNER_DISMISSED_KEY, '1');
  } catch {
    // Memory state already closes the banner. Storage denial must not crash home.
  }
}
