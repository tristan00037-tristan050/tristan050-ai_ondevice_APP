export interface BuildIdentityView {
  readonly contextDigest: string;
  readonly shortCommit: string;
  readonly channel: 'production' | 'development';
}

export function currentBuildIdentity(): BuildIdentityView {
  return {
    contextDigest: __BUILD_CONTEXT_DIGEST__,
    shortCommit: __BUILD_COMMIT__,
    channel: __BUILD_CHANNEL__,
  };
}
