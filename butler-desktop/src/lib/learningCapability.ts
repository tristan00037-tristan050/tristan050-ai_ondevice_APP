import { sidecarFetch, withDeadline } from './sidecarFetch';

export type LearningCapabilityState =
  | 'IN_USE'
  | 'REGISTERED_ONLY'
  | 'PREVIEW_ONLY'
  | 'UNKNOWN';

export type LearningCapabilitySnapshot = Readonly<{
  source: 'CANONICAL_CAPABILITY' | 'UNAVAILABLE';
  generation: number;
  companyRules: LearningCapabilityState;
  companyFacts: LearningCapabilityState;
  companyFormats: LearningCapabilityState;
  folderLearning: LearningCapabilityState;
}>;

export type LearningRowView = Readonly<{
  id:
    | 'company-rules'
    | 'company-facts'
    | 'company-formats'
    | 'folder-learning';
  label: string;
  statusText: string;
  action: 'policy' | 'fact' | 'format' | 'learning';
}>;

const UNKNOWN_SNAPSHOT: LearningCapabilitySnapshot = Object.freeze({
  source: 'UNAVAILABLE',
  generation: 0,
  companyRules: 'UNKNOWN',
  companyFacts: 'UNKNOWN',
  companyFormats: 'UNKNOWN',
  folderLearning: 'UNKNOWN',
});

const STATUS_TEXT: Readonly<Record<LearningCapabilityState, string>> = {
  IN_USE: '쓰이는 중',
  REGISTERED_ONLY: '등록만 됩니다',
  PREVIEW_ONLY: '미리보기만 됩니다',
  UNKNOWN: '확인할 수 없습니다',
};

const CANONICAL_STATES = new Set<LearningCapabilityState>([
  'IN_USE',
  'REGISTERED_ONLY',
  'PREVIEW_ONLY',
]);
const SNAPSHOT_KEYS = new Set([
  'schema_version',
  'source',
  'generation',
  'capabilities',
]);
const CAPABILITY_KEYS = new Set([
  'company_rules',
  'company_facts',
  'company_formats',
  'folder_learning',
]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function capabilityState(value: unknown): LearningCapabilityState {
  return typeof value === 'string' && CANONICAL_STATES.has(value as LearningCapabilityState)
    ? value as LearningCapabilityState
    : 'UNKNOWN';
}

export function parseLearningCapabilitySnapshot(
  value: unknown,
): LearningCapabilitySnapshot {
  if (!isRecord(value)
      || Object.keys(value).length !== SNAPSHOT_KEYS.size
      || Object.keys(value).some(key => !SNAPSHOT_KEYS.has(key))
      || value.schema_version !== 1
      || !Number.isSafeInteger(value.generation)
      || (value.generation as number) < 0
      || !isRecord(value.capabilities)
      || Object.keys(value.capabilities).length !== CAPABILITY_KEYS.size
      || Object.keys(value.capabilities).some(key => !CAPABILITY_KEYS.has(key))) {
    return UNKNOWN_SNAPSHOT;
  }
  if (value.source !== 'CANONICAL') {
    return Object.freeze({
      ...UNKNOWN_SNAPSHOT,
      generation: value.generation as number,
    });
  }
  const states = [
    capabilityState(value.capabilities.company_rules),
    capabilityState(value.capabilities.company_facts),
    capabilityState(value.capabilities.company_formats),
    capabilityState(value.capabilities.folder_learning),
  ] as const;
  if (states.some(state => state === 'UNKNOWN')) return UNKNOWN_SNAPSHOT;
  return Object.freeze({
    source: 'CANONICAL_CAPABILITY',
    generation: value.generation as number,
    companyRules: states[0],
    companyFacts: states[1],
    companyFormats: states[2],
    folderLearning: states[3],
  });
}

export function selectLearningRows(
  snapshot: LearningCapabilitySnapshot | null | undefined,
  expectedGeneration?: number,
): readonly LearningRowView[] {
  const usable = snapshot?.source === 'CANONICAL_CAPABILITY'
    && Number.isSafeInteger(snapshot.generation)
    && snapshot.generation >= 0
    && (
      expectedGeneration === undefined
      || snapshot.generation === expectedGeneration
    );
  const source = usable ? snapshot : UNKNOWN_SNAPSHOT;
  return [
    {
      id: 'company-rules',
      label: '회사 규칙 등록',
      statusText: STATUS_TEXT[source.companyRules],
      action: 'policy',
    },
    {
      id: 'company-facts',
      label: '회사 사실 승인',
      statusText: STATUS_TEXT[source.companyFacts],
      action: 'fact',
    },
    {
      id: 'company-formats',
      label: '회사 양식 등록',
      statusText: STATUS_TEXT[source.companyFormats],
      action: 'format',
    },
    {
      id: 'folder-learning',
      label: '폴더에서 배우기',
      statusText: STATUS_TEXT[source.folderLearning],
      action: 'learning',
    },
  ] as const;
}

/**
 * Reads the canonical capability adapter when the sidecar exposes it.
 * Missing, malformed and unavailable signals remain UNKNOWN; no file or UI
 * fixture is treated as evidence that a capability is in use.
 */
export async function fetchLearningCapabilitySnapshot(
  externalSignal?: AbortSignal,
): Promise<LearningCapabilitySnapshot> {
  try {
    return await withDeadline(async signal => {
      const response = await sidecarFetch('/api/capabilities/learning', { signal });
      if (!response.ok) return UNKNOWN_SNAPSHOT;
      const contentType = response.headers.get('content-type') ?? '';
      if (!/^application\/json(?:;|$)/i.test(contentType)) return UNKNOWN_SNAPSHOT;
      return parseLearningCapabilitySnapshot(await response.json());
    }, { deadlineMs: 3_000, externalSignal });
  } catch {
    return UNKNOWN_SNAPSHOT;
  }
}

export const unavailableLearningCapability = UNKNOWN_SNAPSHOT;
