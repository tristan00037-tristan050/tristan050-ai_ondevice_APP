import { invoke } from '@tauri-apps/api/core';

export type CapabilityTokenProvider = () => Promise<string>;

export async function getSidecarCapabilityToken(): Promise<string> {
  const token = await invoke<string>('get_sidecar_capability_token');
  const trimmed = token.trim();
  if (!trimmed) {
    throw new Error('CAPABILITY_TOKEN_EMPTY');
  }
  return trimmed;
}
