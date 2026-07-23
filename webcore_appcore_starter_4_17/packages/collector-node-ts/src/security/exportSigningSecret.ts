export function requireExportSignSecret(
  environment: NodeJS.ProcessEnv = process.env
): string {
  const value = environment.EXPORT_SIGN_SECRET?.trim();
  if (!value) {
    throw Object.assign(new Error('missing_export_sign_secret'), { status: 503 });
  }
  return value;
}
