/**
 * BFF Base URL resolver
 * - Web: 기본은 현재 origin (same-origin) 사용 가능
 * - 개발 중 BFF가 다른 포트(8081)면 EXPO_PUBLIC_BFF_BASE_URL로 지정
 *
 * 예:
 *   EXPO_PUBLIC_BFF_BASE_URL=http://localhost:8081
 */
export function getBffBaseUrl(): string {
  const env = (process.env.EXPO_PUBLIC_BFF_BASE_URL || "").trim();
  if (env) return env.replace(/\/$/, "");

  // Web에서만 안전하게 origin 사용
  // (native에서는 window가 없으므로 try/catch)
  try {
    // @ts-ignore
    const origin = window?.location?.origin;
    if (origin) return String(origin).replace(/\/$/, "");
  } catch {
    // ignore
  }
  return ""; // 상대경로 fetch를 원하면 "" 유지
}

export function bffUrl(path: string): string {
  const base = getBffBaseUrl();
  if (!path.startsWith("/")) path = `/${path}`;
  // base가 비어 있으면 상대경로로 요청됨 (same-origin)
  return base ? `${base}${path}` : path;
}
