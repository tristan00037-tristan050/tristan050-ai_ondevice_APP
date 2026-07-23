import { sidecarFetch } from '../sidecarFetch';
import type {
  Conversation,
  FolderRecord,
  HomeSnapshot,
  HomeStartupStatus,
  Message,
  MigrationReceipt,
  RuntimeStatus,
  RuntimeTrustCandidate,
  RuntimeTrustReceipt,
  TurnCorrelation,
} from '../../types';

export class HomeApiError extends Error {
  constructor(readonly status: number, readonly code: string) {
    super(`HOME_API_${status}_${code}`);
    this.name = 'HomeApiError';
  }
}

async function json<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let code = 'UNKNOWN';
    try {
      const body = await response.json() as { detail?: { code?: string } };
      code = body.detail?.code ?? code;
    } catch {
      // A non-JSON error body is represented by the generic code only.
    }
    throw new HomeApiError(response.status, code);
  }
  return response.json() as Promise<T>;
}

function mutationHeaders(version?: number): Record<string, string> {
  const requestId = crypto.randomUUID();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'X-Request-ID': requestId,
    'Idempotency-Key': crypto.randomUUID(),
  };
  if (version) headers['If-Match'] = `"v${version}"`;
  return headers;
}

function canonical(value: unknown): string {
  if (value === null || typeof value !== 'object') return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  const object = value as Record<string, unknown>;
  return `{${Object.keys(object).sort().filter(key => object[key] !== undefined).map(key => `${JSON.stringify(key)}:${canonical(object[key])}`).join(',')}}`;
}

async function sha256(value: unknown): Promise<string> {
  const bytes = new TextEncoder().encode(canonical(value));
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('');
}

function migrationConversation(conversation: Conversation): Record<string, unknown> {
  return {
    id: conversation.id,
    ...(conversation.folder_id ? { folder_id: conversation.folder_id } : {}),
    title: conversation.title,
    title_is_custom: conversation.title_is_custom,
    created_at: conversation.created_at,
    updated_at: conversation.updated_at,
    messages: conversation.messages.map(message => ({
      id: message.id,
      role: message.role,
      content: message.content,
      timestamp: message.timestamp,
      ...(message.source ? { source: message.source } : {}),
      ...(message.fact_id ? { fact_id: message.fact_id } : {}),
      ...(message.score === undefined ? {} : { score: message.score }),
    })),
  };
}

async function verifyReceipt(receipt: MigrationReceipt, input: Record<string, unknown>[]): Promise<void> {
  const ids = input.map(item => String(item.id));
  const dispositions = [...receipt.inserted, ...receipt.identical_existing];
  if (!receipt.exact_import || receipt.conflicts.length !== 0 || receipt.item_count !== input.length) {
    throw new Error('MIGRATION_RECEIPT_NOT_EXACT');
  }
  if (new Set(dispositions.map(item => item.id)).size !== input.length) {
    throw new Error('MIGRATION_RECEIPT_ID_SET_MISMATCH');
  }
  const expectedItems = await Promise.all(input.map(async item => ({ id: String(item.id), digest: await sha256(item) })));
  const actual = new Map(dispositions.map(item => [item.id, item.digest]));
  if (expectedItems.some(item => actual.get(item.id) !== item.digest)) {
    throw new Error('MIGRATION_RECEIPT_ITEM_DIGEST_MISMATCH');
  }
  if (receipt.input_digest !== await sha256(input) || receipt.id_set_digest !== await sha256([...ids].sort())) {
    throw new Error('MIGRATION_RECEIPT_INVENTORY_DIGEST_MISMATCH');
  }
}

export async function migrateLegacyConversations(conversations: Conversation[]): Promise<HomeSnapshot> {
  const normalized = conversations.map(migrationConversation);
  const result = await json<{receipt:MigrationReceipt;snapshot:HomeSnapshot}>(await sidecarFetch('/v1/home/migrations/legacy-conversations', {
    method: 'POST',
    headers: mutationHeaders(),
    body: JSON.stringify({ schema_version: 'butler.home.migration.request.v2', migration_id: 'legacy-v2', conversations: normalized }),
  }));
  await verifyReceipt(result.receipt, normalized);
  return result.snapshot;
}

export async function fetchHomeSnapshot(includeTrash = false): Promise<HomeSnapshot> {
  return json(await sidecarFetch(`/v1/home/snapshot?limit=100&include_trash=${includeTrash ? 'true' : 'false'}`));
}

export async function fetchHomeBootstrapStatus(): Promise<HomeStartupStatus> {
  return json(await sidecarFetch('/v1/home/bootstrap-status'));
}

export async function fetchConversationMessages(conversationId: string): Promise<Message[]> {
  const result = await json<{messages:Message[]}>(await sidecarFetch(`/v1/home/conversations/${encodeURIComponent(conversationId)}/messages?limit=100`));
  return result.messages;
}

export async function searchConversations(query: string): Promise<Conversation[]> {
  const result = await json<{conversations:Conversation[]}>(await sidecarFetch(`/v1/home/search?q=${encodeURIComponent(query)}&limit=100`));
  return result.conversations;
}

export async function acceptUserTurn(conversation: Conversation, message: Message): Promise<TurnCorrelation> {
  const payload = {
    conversation: {
      id: conversation.id,
      folder_id: conversation.folder_id ?? null,
      title: conversation.title,
      title_is_custom: conversation.title_is_custom,
      created_at: conversation.created_at,
      updated_at: conversation.updated_at,
    },
    message,
  };
  const receipt = await json<Omit<TurnCorrelation, 'version' | 'folder_id' | 'request_id' | 'durable'> & {command_receipt:{command_id:string}}>(await sidecarFetch(`/v1/home/conversations/${encodeURIComponent(conversation.id)}/turns/user`, {
    method: 'POST', headers: mutationHeaders(conversation.version), body: JSON.stringify(payload),
  }));
  return {
    ...receipt,
    version: receipt.conversation_version,
    folder_id: conversation.folder_id ?? 'system-unclassified',
    request_id: receipt.command_receipt.command_id,
    durable: true,
  };
}

export async function appendAssistantTurn(conversation: Conversation, message: Message, correlation: TurnCorrelation): Promise<{version:number;updated_at:string;request_id:string;durable:true}> {
  if (!conversation.version) throw new Error('HOME_VERSION_REQUIRED');
  const receipt = await json<{committed_at:string;command_receipt:{command_id:string}}>(await sidecarFetch(`/v1/home/conversations/${encodeURIComponent(conversation.id)}/turns/assistant`, {
    method: 'POST', headers: mutationHeaders(conversation.version), body: JSON.stringify({
      turn_id: correlation.turn_id,
      model_request_id: correlation.model_request_id,
      message,
    }),
  }));
  return { version: conversation.version + 1, updated_at: receipt.committed_at, request_id: receipt.command_receipt.command_id, durable: true };
}

export async function recordTerminal(correlation: TurnCorrelation, state: 'FAILED'|'CANCELLED'|'TIMED_OUT', errorCode: string): Promise<void> {
  await json(await sidecarFetch(`/v1/home/model-requests/${encodeURIComponent(correlation.model_request_id)}/terminal`, {
    method: 'POST', headers: mutationHeaders(), body: JSON.stringify({
      conversation_id: correlation.conversation_id,
      turn_id: correlation.turn_id,
      state,
      error_code: errorCode,
    }),
  }));
}

export async function createFolder(name: string, parentId: string | null = null): Promise<FolderRecord> {
  return json(await sidecarFetch('/v1/home/folders', {
    method: 'POST', headers: mutationHeaders(), body: JSON.stringify({ name, parent_id: parentId }),
  }));
}

export async function renameFolder(folder: FolderRecord, name: string): Promise<FolderRecord> {
  return json(await sidecarFetch(`/v1/home/folders/${encodeURIComponent(folder.folder_id)}`, {
    method: 'PATCH', headers: mutationHeaders(folder.version), body: JSON.stringify({name}),
  }));
}

export async function deleteFolder(folder: FolderRecord): Promise<void> {
  await json(await sidecarFetch(`/v1/home/folders/${encodeURIComponent(folder.folder_id)}`, {
    method: 'DELETE', headers: mutationHeaders(folder.version),
  }));
}

export async function moveConversation(conversation: Conversation, folderId: string): Promise<{version:number;folder_id:string;updated_at:string}> {
  if (!conversation.version) throw new Error('HOME_VERSION_REQUIRED');
  return json(await sidecarFetch(`/v1/home/conversations/${encodeURIComponent(conversation.id)}/move`, {
    method: 'POST', headers: mutationHeaders(conversation.version), body: JSON.stringify({ folder_id: folderId }),
  }));
}

export async function renameConversation(conversation: Conversation, title: string): Promise<{title:string;title_is_custom:true;version:number;updated_at:string}> {
  if (!conversation.version) throw new Error('HOME_VERSION_REQUIRED');
  return json(await sidecarFetch(`/v1/home/conversations/${encodeURIComponent(conversation.id)}`, {
    method: 'PATCH', headers: mutationHeaders(conversation.version), body: JSON.stringify({title}),
  }));
}

export async function trashConversation(conversation: Conversation): Promise<{deleted:true;version:number;deleted_at:string}> {
  if (!conversation.version) throw new Error('HOME_VERSION_REQUIRED');
  return json(await sidecarFetch(`/v1/home/conversations/${encodeURIComponent(conversation.id)}`, {
    method: 'DELETE', headers: mutationHeaders(conversation.version),
  }));
}

export async function restoreConversation(conversation: Conversation, folderId = 'system-unclassified'): Promise<{restored:true;folder_id:string;version:number;updated_at:string}> {
  if (!conversation.version) throw new Error('HOME_VERSION_REQUIRED');
  return json(await sidecarFetch(`/v1/home/conversations/${encodeURIComponent(conversation.id)}/restore`, {
    method: 'POST', headers: mutationHeaders(conversation.version), body: JSON.stringify({folder_id:folderId}),
  }));
}

export async function permanentlyDeleteConversation(conversation: Conversation): Promise<void> {
  if (!conversation.version) throw new Error('HOME_VERSION_REQUIRED');
  await json(await sidecarFetch(`/v1/home/trash/${encodeURIComponent(conversation.id)}`, {
    method: 'DELETE', headers: {...mutationHeaders(conversation.version), 'X-Permanent-Delete': 'confirm'},
  }));
}

export async function fetchRuntimeStatus(): Promise<RuntimeStatus> {
  return json(await sidecarFetch('/v1/home/runtime-status'));
}

export async function fetchAndPersistRuntimeTrustReceipt(): Promise<RuntimeTrustReceipt> {
  const candidate = await json<RuntimeTrustCandidate>(await sidecarFetch('/v1/home/runtime-trust-candidate'));
  if (candidate.runtime_activation_allowed !== false) {
    throw new Error('RUNTIME_TRUST_CANDIDATE_INVALID');
  }
  const storedGeneration = Number.parseInt(localStorage.getItem('butler.firstscreen.trust-generation') ?? '0', 10);
  const expectedGeneration = Number.isSafeInteger(storedGeneration) && storedGeneration >= 0 ? storedGeneration : 0;
  const { invoke } = await import('@tauri-apps/api/core');
  const persisted = await invoke<RuntimeTrustReceipt>('verify_and_commit_trust_update', {
    request: {
      schema_version: 'butler.firstscreen.verify-and-commit.v2',
      request_id: crypto.randomUUID(),
      expected_generation: expectedGeneration,
      environment: candidate.environment,
      root_json: candidate.root_json,
      revocations_json: candidate.revocations_json,
      decision_json: candidate.decision_json,
      release_subjects_json: candidate.release_subjects_json,
      source_commit_oid: candidate.source_commit_oid,
      source_tree_oid: candidate.source_tree_oid,
      native_build_identity_digest: candidate.native_build_identity_digest,
    },
  });
  if (
    persisted.status !== 'VERIFIED_AND_COMMITTED'
    || persisted.generation_before !== expectedGeneration
    || persisted.generation_after !== expectedGeneration + 1
    || persisted.runtime_activation_allowed !== false
  ) {
    throw new Error('RUNTIME_TRUST_RECEIPT_NATIVE_MISMATCH');
  }
  localStorage.setItem('butler.firstscreen.trust-generation', String(persisted.generation_after));
  return persisted;
}

export async function fetchIntegrityStatus(): Promise<{ok:boolean;database_mode:string;directory_mode:string;encrypted_message_content:boolean}> {
  return json(await sidecarFetch('/v1/home/integrity'));
}
