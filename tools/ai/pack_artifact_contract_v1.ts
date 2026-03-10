// AI-ALGO: PACK_ARTIFACT_CONTRACT_V1
// 알고리즘팀 산출물 — 팩 아티팩트 존재 검증 (verifyPackArtifactsV1)

export const REQUIRED_ARTIFACTS = [
  'model.onnx',
  'tokenizer.json',
  'config.json',
  'chat_template.jinja',
  'runtime_manifest.json',
  'SHA256SUMS',
] as const;

export type RequiredArtifact = typeof REQUIRED_ARTIFACTS[number];

export interface PackArtifactVerifyResultV1 {
  logical_pack_id: string;
  pack_dir: string;
  missing: string[];
  present: string[];
  ok: boolean;
}

export function verifyPackArtifactsV1(
  logical_pack_id: string,
  pack_dir: string,
  existing_files: string[],
): PackArtifactVerifyResultV1 {
  const present: string[] = [];
  const missing: string[] = [];
  for (const artifact of REQUIRED_ARTIFACTS) {
    if (existing_files.includes(artifact)) {
      present.push(artifact);
    } else {
      missing.push(artifact);
    }
  }
  return {
    logical_pack_id,
    pack_dir,
    missing,
    present,
    ok: missing.length === 0,
  };
}

export function assertPackArtifactsCompleteV1(result: PackArtifactVerifyResultV1): void {
  if (!result.ok) {
    throw new Error(`PACK_ARTIFACTS_MISSING:${result.logical_pack_id}:${result.missing.join(',')}`);
  }
}
