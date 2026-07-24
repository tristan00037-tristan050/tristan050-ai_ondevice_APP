import { sidecarFetch } from '../sidecarFetch';
import type {
  Conversation,
  ConversationMessageLoadResult,
  FolderRecord,
  HomeSnapshot,
  HomeStartupStatus,
  Message,
  MigrationReceipt,
  RuntimeStatus,
  RuntimeTrustCandidate,
  RuntimeTrustReceipt,
  RuntimeTrustStatus,
  TurnCorrelation,
} from '../../types';

export class HomeApiError extends Error {
  constructor(readonly status: number, readonly code: string) {
    super(`HOME_API_${status}_${code}`);
    this.name = 'HomeApiError';
  }
}

export class HomePaginationError extends Error {
  constructor(
    readonly code: string,
    readonly partialSnapshot: HomeSnapshot | null = null,
  ) {
    super(code);
    this.name = 'HomePaginationError';
  }
}

const HOME_PAGE_LIMIT = 100;
const MAX_HOME_PAGES = 10_000;

function isSafeCount(value: unknown): value is number {
  return Number.isSafeInteger(value) && Number(value) >= 0;
}

function isDigest(value: unknown): value is string {
  return typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
}

function abortError(): DOMException {
  return new DOMException('Aborted', 'AbortError');
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

export async function fetchHomeSnapshot(
  includeTrash = false,
  options: { signal?: AbortSignal; profileId?: string | null } = {},
): Promise<HomeSnapshot> {
  let cursor: string | null = null;
  let aggregate: HomeSnapshot | null = null;
  const seenCursors = new Set<string>();
  const seenIds = new Set<string>();
  let pages = 0;
  try {
    while (true) {
      if (options.signal?.aborted) throw abortError();
      if (++pages > MAX_HOME_PAGES) {
        throw new HomePaginationError('HOME_SNAPSHOT_PAGE_LIMIT', aggregate);
      }
      const query = new URLSearchParams({
        limit: String(HOME_PAGE_LIMIT),
        include_trash: includeTrash ? 'true' : 'false',
      });
      if (cursor !== null) query.set('cursor', cursor);
      if (options.profileId) query.set('profile_id', options.profileId);
      const page = await json<HomeSnapshot>(await sidecarFetch(
        `/v1/home/snapshot?${query.toString()}`,
        { signal: options.signal },
      ));
      if (
        page.schema_version !== 'butler.home.snapshot.v2'
        || !Array.isArray(page.conversations)
        || !Array.isArray(page.folders)
        || !Array.isArray(page.partial_errors)
        || !isSafeCount(page.total_conversation_count)
        || !isSafeCount(page.filtered_conversation_count)
        || !isDigest(page.inventory_digest)
        || page.active_profile_filter !== (options.profileId ?? null)
      ) {
        throw new HomePaginationError('HOME_SNAPSHOT_SCHEMA_INVALID', aggregate);
      }
      if (aggregate === null) {
        aggregate = { ...page, conversations: [], partial_errors: [] };
      } else if (
        page.workspace_id !== aggregate.workspace_id
        || page.inventory_digest !== aggregate.inventory_digest
        || page.filtered_conversation_count !== aggregate.filtered_conversation_count
        || page.total_conversation_count !== aggregate.total_conversation_count
        || page.read_only !== aggregate.read_only
      ) {
        throw new HomePaginationError('HOME_SNAPSHOT_CHANGED_DURING_READ', aggregate);
      }
      for (const conversation of page.conversations) {
        if (!conversation || typeof conversation.id !== 'string' || seenIds.has(conversation.id)) {
          throw new HomePaginationError('HOME_SNAPSHOT_DUPLICATE_OR_INVALID_ID', aggregate);
        }
        if (!isSafeCount(conversation.message_count)) {
          throw new HomePaginationError('HOME_MESSAGE_COUNT_REQUIRED', aggregate);
        }
        seenIds.add(conversation.id);
        aggregate.conversations.push(conversation);
      }
      const errorKeys = new Set(
        aggregate.partial_errors.map(error => `${error.conversation_id}:${error.code}`),
      );
      for (const error of page.partial_errors) {
        const key = `${error.conversation_id}:${error.code}`;
        if (!errorKeys.has(key)) {
          aggregate.partial_errors.push(error);
          errorKeys.add(key);
        }
      }
      const next = page.next_cursor;
      if (next === null) break;
      if (typeof next !== 'string' || next.length === 0 || seenCursors.has(next)) {
        throw new HomePaginationError('HOME_SNAPSHOT_CURSOR_LOOP', aggregate);
      }
      if (page.conversations.length === 0) {
        throw new HomePaginationError('HOME_SNAPSHOT_EMPTY_PAGE_WITH_CURSOR', aggregate);
      }
      seenCursors.add(next);
      cursor = next;
    }
    if (aggregate === null) {
      throw new HomePaginationError('HOME_SNAPSHOT_EMPTY_RESPONSE');
    }
    const computedInventory = await sha256(
      aggregate.conversations.map(item => [item.updated_at, item.id]),
    );
    if (
      aggregate.conversations.length !== aggregate.filtered_conversation_count
      || computedInventory !== aggregate.inventory_digest
      || aggregate.partial_errors.length !== 0
    ) {
      throw new HomePaginationError('HOME_SNAPSHOT_INVENTORY_INCOMPLETE', aggregate);
    }
    aggregate.next_cursor = null;
    return aggregate;
  } catch (error) {
    if (error instanceof HomePaginationError) throw error;
    if (options.signal?.aborted) throw abortError();
    throw new HomePaginationError(
      aggregate ? 'HOME_SNAPSHOT_PAGE_FAILED' : 'HOME_SNAPSHOT_FAILED',
      aggregate,
    );
  }
}

export async function fetchHomeBootstrapStatus(): Promise<HomeStartupStatus> {
  return json(await sidecarFetch('/v1/home/bootstrap-status'));
}

export async function fetchConversationMessages(
  conversationId: string,
  expectedCount: number,
  options: {
    signal?: AbortSignal;
    initialItems?: Message[];
    conversationVersion?: number | null;
  } = {},
): Promise<ConversationMessageLoadResult> {
  const failed = (
    status: Exclude<ConversationMessageLoadResult['status'], 'READY'>,
    messages: Message[],
    code: string,
    nextSequence: number | null,
    locked = false,
    partialErrors: Array<{ sequence: number; code: string }> = [
      { sequence: nextSequence ?? 0, code },
    ],
  ): ConversationMessageLoadResult => ({
    status,
    conversation_id: conversationId,
    conversation_version: options.conversationVersion ?? null,
    messages,
    expected_count: expectedCount,
    loaded_count: messages.length,
    next_sequence: nextSequence,
    partial_errors: partialErrors,
    locked,
    error_code: code,
  });

  if (!isSafeCount(expectedCount)) {
    return failed(
      'ERROR',
      [],
      'HOME_MESSAGE_COUNT_REQUIRED',
      null,
      false,
      [],
    );
  }
  const messages = [...(options.initialItems ?? [])];
  const ids = new Set<string>();
  for (let index = 0; index < messages.length; index += 1) {
    const item = messages[index];
    if (
      item.sequence !== index + 1
      || typeof item.id !== 'string'
      || ids.has(item.id)
    ) {
      return failed(
        'PARTIAL',
        messages,
        'HOME_MESSAGE_INITIAL_INVENTORY_INVALID',
        null,
      );
    }
    ids.add(item.id);
  }
  if (messages.length > expectedCount) {
    return failed(
      'PARTIAL',
      messages,
      'HOME_MESSAGE_COUNT_MISMATCH',
      null,
    );
  }
  let afterSequence = messages.length;
  let pages = 0;
  try {
    while (true) {
      if (options.signal?.aborted) throw abortError();
      if (++pages > MAX_HOME_PAGES) {
        return failed(
          'PARTIAL',
          messages,
          'HOME_MESSAGE_PAGE_LIMIT',
          afterSequence || null,
        );
      }
      const result = await json<{
        schema_version: string;
        conversation_id: string;
        messages: Message[];
        message_count: number;
        conversation_version: number;
        next_sequence: number | null;
        partial_errors: Array<{ sequence: number; code: string }>;
        locked: boolean;
      }>(await sidecarFetch(
        `/v1/home/conversations/${encodeURIComponent(conversationId)}/messages?limit=${HOME_PAGE_LIMIT}&after_sequence=${afterSequence}`,
        { signal: options.signal },
      ));
      if (
        result.schema_version !== 'butler.home.messages.v2'
        || result.conversation_id !== conversationId
        || !Array.isArray(result.messages)
        || !Array.isArray(result.partial_errors)
        || !isSafeCount(result.message_count)
        || result.message_count !== expectedCount
        || !isSafeCount(result.conversation_version)
        || (
          options.conversationVersion !== undefined
          && options.conversationVersion !== null
          && result.conversation_version !== options.conversationVersion
        )
      ) {
        return failed(
          messages.length ? 'PARTIAL' : 'ERROR',
          messages,
          'HOME_MESSAGE_RESPONSE_SCHEMA_INVALID',
          afterSequence || null,
        );
      }
      if (result.locked) {
        return failed(
          'LOCKED',
          messages,
          'HOME_STORE_LOCKED',
          null,
          true,
          [],
        );
      }
      let expectedSequence = afterSequence + 1;
      for (const item of result.messages) {
        if (
          !isSafeCount(item.sequence)
          || item.sequence !== expectedSequence
          || item.sequence === 0
          || typeof item.id !== 'string'
          || ids.has(item.id)
        ) {
          return failed(
            'PARTIAL',
            messages,
            'HOME_MESSAGE_SEQUENCE_GAP',
            afterSequence || null,
          );
        }
        ids.add(item.id);
        messages.push(item);
        afterSequence = item.sequence;
        expectedSequence += 1;
      }
      if (result.partial_errors.length !== 0) {
        const partialErrors = result.partial_errors.map(error => ({
          sequence: error.sequence,
          code: error.code || 'HOME_MESSAGE_PARTIAL_ERROR',
        }));
        return failed(
          'PARTIAL',
          messages,
          partialErrors[0]?.code ?? 'HOME_MESSAGE_PARTIAL_ERROR',
          afterSequence || null,
          false,
          partialErrors,
        );
      }
      if (result.next_sequence === null) {
        const contiguous = messages.every(
          (item, index) => item.sequence === index + 1,
        );
        if (
          !contiguous
          || messages.length !== expectedCount
          || (expectedCount > 0 && afterSequence !== expectedCount)
        ) {
          return failed(
            'PARTIAL',
            messages,
            'HOME_MESSAGE_INVENTORY_INCOMPLETE',
            null,
          );
        }
        return {
          status: 'READY',
          conversation_id: conversationId,
          conversation_version: result.conversation_version,
          messages,
          expected_count: expectedCount,
          loaded_count: messages.length,
          next_sequence: null,
          partial_errors: [],
          locked: false,
          error_code: null,
        };
      }
      if (
        !Number.isSafeInteger(result.next_sequence)
        || result.next_sequence <= 0
        || result.messages.length === 0
        || result.next_sequence !== afterSequence
        || afterSequence >= expectedCount
      ) {
        return failed(
          'PARTIAL',
          messages,
          result.messages.length === 0
            ? 'HOME_MESSAGE_EMPTY_PAGE_WITH_CURSOR'
            : 'HOME_MESSAGE_CURSOR_INVALID',
          afterSequence || null,
        );
      }
    }
  } catch {
    if (options.signal?.aborted) throw abortError();
    return failed(
      messages.length ? 'PARTIAL' : 'ERROR',
      messages,
      'HOME_MESSAGE_PAGE_FAILED',
      afterSequence || null,
    );
  }
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
  const { invoke } = await import('@tauri-apps/api/core');
  const nativeStatus = await invoke<RuntimeTrustStatus>('get_runtime_trust_status');
  if (
    nativeStatus.authority !== 'rust-native'
    || !Number.isSafeInteger(nativeStatus.generation)
    || nativeStatus.generation < 0
    || nativeStatus.runtime_activation_allowed !== false
  ) {
    throw new Error('RUNTIME_TRUST_NATIVE_STATUS_INVALID');
  }
  // Browser storage is a disposable display cache. Native Keychain state is
  // authoritative and heals missing, stale, or malformed renderer state.
  const cachedGeneration = Number.parseInt(
    localStorage.getItem('butler.firstscreen.trust-generation') ?? '',
    10,
  );
  if (cachedGeneration !== nativeStatus.generation) {
    localStorage.setItem(
      'butler.firstscreen.trust-generation',
      String(nativeStatus.generation),
    );
  }
  const candidate = await json<RuntimeTrustCandidate>(await sidecarFetch('/v1/home/runtime-trust-candidate'));
  if (candidate.runtime_activation_allowed !== false) {
    throw new Error('RUNTIME_TRUST_CANDIDATE_INVALID');
  }
  const expectedGeneration = nativeStatus.generation;
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
  const confirmedStatus = await invoke<RuntimeTrustStatus>('get_runtime_trust_status');
  if (
    confirmedStatus.generation !== persisted.generation_after
    || confirmedStatus.previous_trusted_state_receipt_digest !== persisted.receipt_digest
  ) {
    throw new Error('RUNTIME_TRUST_RECEIPT_NATIVE_MISMATCH');
  }
  return persisted;
}

export async function fetchIntegrityStatus(): Promise<{ok:boolean;database_mode:string;directory_mode:string;encrypted_message_content:boolean}> {
  return json(await sidecarFetch('/v1/home/integrity'));
}
