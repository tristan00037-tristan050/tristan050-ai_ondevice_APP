import Constants from "expo-constants";
import { Platform } from "react-native";

function trimSlash(s: string) {
  return s.replace(/\/+$/, "");
}

/**
 * HUD -> BFF(OS Gateway) base URL resolver
 * - Live: BFF(8081)로 고정
 * - Mock: 네트워크 호출 자체가 NO-OP 이므로 base URL은 사용되지 않아도 됨
 */
export function resolveBffBaseUrl(): string {
  const explicit = process.env.EXPO_PUBLIC_BFF_BASE_URL;
  if (explicit) return trimSlash(explicit);

  // Web: same hostname, BFF port 8081
  if (Platform.OS === "web" && typeof window !== "undefined") {
    const { protocol, hostname } = window.location;
    return `${protocol}//${hostname}:8081`;
  }

  // Native dev: infer host from Expo config
  const hostUri =
    (Constants.expoConfig as any)?.hostUri ??
    (Constants.manifest2 as any)?.extra?.expoClient?.hostUri ??
    (Constants.manifest as any)?.hostUri;

  const host = typeof hostUri === "string" ? hostUri.split(":")[0] : undefined;
  if (host) return `http://${host}:8081`;

  return "http://127.0.0.1:8081";
}

export function bffUrl(path: string): string {
  const base = resolveBffBaseUrl();
  const p = path.startsWith("/") ? path : `/${path}`;
  return `${base}${p}`;
}

