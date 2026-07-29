import { sidecarFetch, withDeadline } from './sidecarFetch';

export type LearningCapabilityState =
  | 'IN_USE'
  | 'REGISTERED'
  | 'NOT_REGISTERED'
  | 'UNAVAILABLE';

export type LearningCapabilitySnapshot = Readonly<{
  source: 'CANONICAL_CAPABILITY' | 'UNAVAILABLE';
  snapshotRevision: string | null;
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

const UNAVAILABLE_SNAPSHOT: LearningCapabilitySnapshot = Object.freeze({
  source: 'UNAVAILABLE',
  snapshotRevision: null,
  generation: 0,
  companyRules: 'UNAVAILABLE',
  companyFacts: 'UNAVAILABLE',
  companyFormats: 'UNAVAILABLE',
  folderLearning: 'UNAVAILABLE',
});

const STATUS_TEXT: Readonly<Record<LearningCapabilityState, string>> = {
  IN_USE: '쓰이는 중',
  REGISTERED: '등록됨',
  NOT_REGISTERED: '등록되지 않음',
  UNAVAILABLE: '확인할 수 없습니다',
};

const CANONICAL_STATES = new Set<LearningCapabilityState>([
  'IN_USE',
  'REGISTERED',
  'NOT_REGISTERED',
  'UNAVAILABLE',
]);
const SNAPSHOT_KEYS = new Set([
  'schema_version',
  'source',
  'snapshot_revision',
  'generation',
  'capabilities',
]);
const CAPABILITY_KEYS = new Set([
  'company_policy',
  'company_fact',
  'company_format',
  'folder_learning',
]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function capabilityState(value: unknown): LearningCapabilityState {
  return typeof value === 'string' && CANONICAL_STATES.has(value as LearningCapabilityState)
    ? value as LearningCapabilityState
    : 'UNAVAILABLE';
}

export function parseLearningCapabilitySnapshot(
  value: unknown,
): LearningCapabilitySnapshot {
  if (!isRecord(value)
      || Object.keys(value).length !== SNAPSHOT_KEYS.size
      || Object.keys(value).some(key => !SNAPSHOT_KEYS.has(key))
      || value.schema_version !== 2
      || typeof value.snapshot_revision !== 'string'
      || !/^[0-9a-f]{64}$/.test(value.snapshot_revision)
      || !Number.isSafeInteger(value.generation)
      || (value.generation as number) < 0
      || !isRecord(value.capabilities)
      || Object.keys(value.capabilities).length !== CAPABILITY_KEYS.size
      || Object.keys(value.capabilities).some(key => !CAPABILITY_KEYS.has(key))) {
    return UNAVAILABLE_SNAPSHOT;
  }
  if (value.source !== 'CANONICAL') {
    return Object.freeze({
      ...UNAVAILABLE_SNAPSHOT,
      generation: value.generation as number,
    });
  }
  const states = [
    capabilityState(value.capabilities.company_policy),
    capabilityState(value.capabilities.company_fact),
    capabilityState(value.capabilities.company_format),
    capabilityState(value.capabilities.folder_learning),
  ] as const;
  if (states.some(state => state === 'UNAVAILABLE')) return UNAVAILABLE_SNAPSHOT;
  return Object.freeze({
    source: 'CANONICAL_CAPABILITY',
    snapshotRevision: value.snapshot_revision,
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
  const source = usable ? snapshot : UNAVAILABLE_SNAPSHOT;
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
      if (!response.ok) return UNAVAILABLE_SNAPSHOT;
      const contentType = response.headers.get('content-type') ?? '';
      if (!/^application\/json(?:;|$)/i.test(contentType)) return UNAVAILABLE_SNAPSHOT;
      return parseLearningCapabilitySnapshot(await response.json());
    }, { deadlineMs: 3_000, externalSignal });
  } catch {
    return UNAVAILABLE_SNAPSHOT;
  }
}

export const unavailableLearningCapability = UNAVAILABLE_SNAPSHOT;
