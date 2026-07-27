import React, {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useReducer,
  useRef,
  useState,
} from 'react';
import { flushSync } from 'react-dom';
import { getVersion } from '@tauri-apps/api/app';
import { sidecarFetch, uiSafeSidecarErrorMessage } from './lib/sidecarFetch';
import butlerIconStaticUrl from './assets/butler-icon-static.svg';
import { EgressBadge } from './components/EgressBadge';
import { Sidebar } from './components/chat/Sidebar';
import { ChatInput } from './components/chat/ChatInput';
import { MessageList } from './components/chat/MessageList';
import { DeleteConfirmModal } from './components/chat/DeleteConfirmModal';
import { CardGrid } from './components/v1_1/CardGrid';
import { SettingsShell, type SettingsAction } from './components/home/SettingsShell';
import { SetupBanner } from './components/home/SetupBanner';
import { FormFillModal } from './components/v1_1/FormFillModal';
import { DocumentReviewModal } from './components/v1_1/DocumentReviewModal';
import { SIDECAR_BASE } from './constants';
import { useEgressReport } from './lib/egressReport';
import { useSetupState } from './lib/useSetupState';
import type { SSEEvent, Conversation, Message, FolderRecord, RuntimeStatus, RuntimeTrustReceipt, HomeStartupStatus, TurnCorrelation, HomeInventoryState } from './types';
import {
  loadConversations,
  generateId,
  clearLegacyConversations,
} from './lib/storage';
import {
  acceptUserTurn,
  appendAssistantTurn,
  createFolder,
  deleteFolder,
  fetchConversationMessages,
  fetchHomeBootstrapStatus,
  fetchHomeSnapshot,
  fetchRuntimeStatus,
  fetchAndPersistRuntimeTrustReceipt,
  HomeApiError,
  HomePaginationError,
  migrateLegacyConversations,
  moveConversation,
  permanentlyDeleteConversation,
  recordTerminal,
  renameConversation,
  renameFolder,
  restoreConversation,
  searchConversations,
  trashConversation,
} from './lib/home/client';
import { MutationQueue } from './lib/home/mutationQueue';
import {
  assessMessageInventory,
  candidateFromRecord,
  canMutateConversation,
  messageInventoryReducer,
  type MessageInventoryMap,
} from './lib/home/messageInventory';

const EgressMonitor = lazy(() => import('./components/chat/EgressMonitor').then(module => ({ default: module.EgressMonitor })));
const AccountingModal = lazy(() => import('./components/chat/AccountingModal').then(module => ({ default: module.AccountingModal })));
const RequestParsingModal = lazy(() => import('./components/chat/RequestParsingModal').then(module => ({ default: module.RequestParsingModal })));
const Card2DocumentTransform = lazy(() => import('./components/v1_1/Card2DocumentTransform').then(module => ({ default: module.Card2DocumentTransform })));
const Box3DraftModal = lazy(() => import('./components/v1_1/Box3DraftModal').then(module => ({ default: module.Box3DraftModal })));
const AdminPolicyConsole = lazy(() => import('./components/v1_1/AdminPolicyConsole').then(module => ({ default: module.AdminPolicyConsole })));
const CompanyFormatConsole = lazy(() => import('./components/v1_1/CompanyFormatConsole').then(module => ({ default: module.CompanyFormatConsole })));
const CompanyFactApprovalConsole = lazy(() => import('./components/v1_1/CompanyFactApprovalConsole').then(module => ({ default: module.CompanyFactApprovalConsole })));
const CompanyLearningConsole = lazy(() => import('./components/v1_1/CompanyLearningConsole').then(module => ({ default: module.CompanyLearningConsole })));

type PendingBotState = {
  source: 'factpack' | 'llm' | null;
  loadingStatus: string;
  progressPercent?: number;
  streamBuffer: string;
  content: string | null;
  isError: boolean;
  factId?: string;
  score?: number;
};

const CARD_MODE_MAP: Record<number, string> = {
  1: 'request_organize',
  2: 'format_convert',
  3: 'new_draft',
  4: 'document_review',
  5: 'accounting_classify',
  6: 'form_fill',
};

const CARD_MODE_ID_BY_MODE: Record<string, string> = Object.fromEntries(
  Object.entries(CARD_MODE_MAP).map(([id, mode]) => [mode, id])
);
CARD_MODE_ID_BY_MODE.attachment_edit = '4';

export function sidecarCardMode(mode: string): string {
  if (mode === 'free') return 'free';
  return CARD_MODE_ID_BY_MODE[mode] ?? 'free';
}

export function App() {
  const setupUiState = useSetupState();
  const legacyConversationsRef = useRef<Conversation[]>(loadConversations());
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [trashedConversations, setTrashedConversations] = useState<Conversation[]>([]);
  const [activeConvId, setActiveConvId] = useState<string | null>(null);
  const [pendingBot, setPendingBot] = useState<PendingBotState | null>(null);
  const [processing, setProcessing] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const [cardMode, setCardMode] = useState<string>('free');
  const [accountingModalOpen, setAccountingModalOpen] = useState(false);
  const [requestParsingModalOpen, setRequestParsingModalOpen] = useState(false);
  const [documentTransformModalOpen, setDocumentTransformModalOpen] = useState(false);
  const [box3DraftModalOpen, setBox3DraftModalOpen] = useState(false);
  const [formFillModalOpen, setFormFillModalOpen] = useState(false);
  const [documentReviewModalOpen, setDocumentReviewModalOpen] = useState(false);
  const [adminPolicyConsoleOpen, setAdminPolicyConsoleOpen] = useState(false);
  const [companyFormatConsoleOpen, setCompanyFormatConsoleOpen] = useState(false);
  const [companyFactConsoleOpen, setCompanyFactConsoleOpen] = useState(false);
  const [companyLearningConsoleOpen, setCompanyLearningConsoleOpen] = useState(false);
  const [egressMonitorOpen, setEgressMonitorOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [folders, setFolders] = useState<FolderRecord[]>([]);
  const [, setRuntimeStatus] = useState<RuntimeStatus|null>(null);
  const [, setRuntimeTrustReceipt] = useState<RuntimeTrustReceipt|null>(null);
  const [, setRuntimeTrustState] = useState<'verified'|'blocked'|'recovery'|'unavailable'>('unavailable');
  const [homeStoreError, setHomeStoreError] = useState<string|null>(null);
  const [homeStartup, setHomeStartup] = useState<HomeStartupStatus|null>(null);
  const [homeReadOnly, setHomeReadOnly] = useState(true);
  const [homeLoading, setHomeLoading] = useState(true);
  const [homeInventoryState, setHomeInventoryState] = useState<HomeInventoryState>('LOADING');
  const [messageInventories, dispatchMessageInventory] = useReducer(
    messageInventoryReducer,
    {},
  );
  const [conflictNotice, setConflictNotice] = useState<string | null>(null);
  const [sidecarReady, setSidecarReady] = useState(false);
  const [sidecarElapsed, setSidecarElapsed] = useState(0);
  const [sidecarFailed, setSidecarFailed] = useState(false);
  // 헤더 버전 표시: 앱 버전(getVersion, 실패 시 빌드시 주입값으로 폴백), 엔진 버전(/health)
  const [appVersion, setAppVersion] = useState<string>(__APP_VERSION__);
  const [engineVersion, setEngineVersion] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const conversationsRef = useRef<Conversation[]>([]);
  const queueRef = useRef(new MutationQueue());
  const processingConversationRef = useRef<string | null>(null);
  const searchTimerRef = useRef<number>(0);
  const messageLoadAbortRef = useRef<AbortController | null>(null);
  const messageLoadGenerationRef = useRef(0);
  const messageInventoriesRef = useRef<MessageInventoryMap>({});
  const egressBadgeRef = useRef<HTMLButtonElement>(null);
  const { state: egressState, refresh: refreshEgress } = useEgressReport();

  useEffect(() => {
    conversationsRef.current = conversations;
  }, [conversations]);

  useEffect(() => {
    messageInventoriesRef.current = messageInventories;
  }, [messageInventories]);

  useEffect(() => () => window.clearTimeout(searchTimerRef.current), []);

  const mergeLoadedMessages = useCallback((rows: Conversation[]) => {
    const current = new Map(conversationsRef.current.map(conversation => [conversation.id, conversation.messages]));
    return rows.map(conversation => ({
      ...conversation,
      messages: current.get(conversation.id)
        ?? (Array.isArray(conversation.messages) ? conversation.messages : []),
    }));
  }, []);

  const refreshHome = useCallback(async () => {
    setHomeInventoryState('LOADING');
    try {
      const loadSnapshot = async (includeTrash: boolean) => {
        try {
          return { snapshot: await fetchHomeSnapshot(includeTrash), complete: true };
        } catch (error) {
          if (error instanceof HomePaginationError && error.partialSnapshot) {
            return { snapshot: error.partialSnapshot, complete: false };
          }
          throw error;
        }
      };
      const [activeResult, trashResult, runtime] = await Promise.all([
        loadSnapshot(false),
        loadSnapshot(true),
        fetchRuntimeStatus(),
      ]);
      const active = activeResult.snapshot;
      const trash = trashResult.snapshot;
      const inventoryComplete = activeResult.complete && trashResult.complete;
      setFolders(active.folders);
      setConversations(mergeLoadedMessages(active.conversations));
      setTrashedConversations(trash.conversations.map(conversation => ({
        ...conversation,
        messages: Array.isArray(conversation.messages)
          ? conversation.messages
          : [],
      })));
      setRuntimeStatus(runtime);
      try {
        setRuntimeTrustReceipt(await fetchAndPersistRuntimeTrustReceipt());
        setRuntimeTrustState('verified');
      } catch (error) {
        setRuntimeTrustReceipt(null);
        const code = String(error);
        setRuntimeTrustState(
          code.includes('BLOCK_TRUST_STATE_MISSING_OR_ROLLBACK') || code.includes('BLOCK_TRUST_STATE_CAS')
            ? 'recovery'
            : code.includes('UNVERIFIED_PLATFORM_EVIDENCE_MISSING')
              ? 'unavailable'
              : 'blocked',
        );
      }
      setHomeStartup(active.startup);
      setHomeReadOnly(active.read_only || !inventoryComplete);
      setHomeInventoryState(inventoryComplete ? 'COMPLETE' : 'PARTIAL');
      setHomeLoading(false);
      setHomeStoreError(inventoryComplete
        ? null
        : '대화 목록 일부만 복원되었습니다. 누락 방지를 위해 저장과 전송을 차단했습니다.');
    } catch (error) {
      setHomeInventoryState('ERROR');
      setHomeLoading(false);
      setHomeReadOnly(true);
      throw error;
    }
  }, [mergeLoadedMessages]);

  const reportMutationFailure = useCallback(async (error: unknown, label: string) => {
    if (error instanceof HomeApiError && error.status === 409) {
      setConflictNotice('다른 변경 사항이 먼저 저장되어 서버의 최신 상태를 다시 불러왔습니다. 내용을 확인해 주십시오.');
    } else {
      setHomeStoreError(`${label} 저장하지 못했습니다. 저장소를 다시 확인합니다.`);
    }
    try {
      await refreshHome();
    } catch {
      setHomeReadOnly(true);
      setHomeStoreError('대화 저장소에 연결할 수 없어 읽기 전용으로 전환했습니다. 입력 내용은 유지됩니다.');
    }
  }, [refreshHome]);

  useEffect(() => {
    if (!sidecarReady) return;
    let cancelled = false;
    const bootstrap = async () => {
      try {
        const startup = await fetchHomeBootstrapStatus();
        if (cancelled) return;
        setHomeStartup(startup);
        if (startup.status !== 'HOME_READY') {
          await refreshHome();
          if (!cancelled) {
            const statusMessage: Partial<Record<HomeStartupStatus['status'], string>> = {
              READ_ONLY_WORKSPACE_MIRROR_MISSING: '작업공간 확인 파일이 없어 기존 데이터를 읽기 전용으로 보호하고 있습니다.',
              READ_ONLY_WORKSPACE_CONFLICT: '작업공간 정보가 일치하지 않아 기존 데이터를 읽기 전용으로 보호하고 있습니다.',
              READ_ONLY_KEY_MISSING: '암호화 키를 찾지 못해 대화 내용이 잠겼습니다. 새 키나 저장소는 만들지 않았습니다.',
              READ_ONLY_KEY_ID_CONFLICT: '암호화 키 식별자가 일치하지 않아 대화 내용이 잠겼습니다.',
              READ_ONLY_DB_INTEGRITY_FAILED: '저장소 무결성 확인에 실패하여 쓰기 작업을 차단했습니다.',
              READ_ONLY_STORAGE_GUARD_FAILED: '저장 경계 검증에 실패하여 쓰기 작업을 차단했습니다.',
              MIGRATION_BLOCKED: '저장소 이전을 안전하게 완료할 수 없어 원본을 보존했습니다.',
            };
            setHomeStoreError(`${statusMessage[startup.status] ?? '대화 저장소가 읽기 전용입니다.'} 지원 코드: ${startup.support_code}`);
          }
          return;
        }
        const legacy = legacyConversationsRef.current;
        if (legacy.length) {
          const migrated = await migrateLegacyConversations(legacy);
          if (cancelled) return;
          setFolders(migrated.folders);
          setConversations(mergeLoadedMessages(migrated.conversations));
          clearLegacyConversations();
          legacyConversationsRef.current = [];
        }
        if (!cancelled) await refreshHome();
      } catch (error) {
        if (cancelled) return;
        setHomeReadOnly(true);
        setHomeLoading(false);
        setHomeStoreError(error instanceof HomeApiError && error.status === 409
          ? '기존 대화와 제품 저장소의 내용이 달라 자동 이전을 중단했습니다. 브라우저 원본은 보존했습니다.'
          : '대화 저장소를 불러오지 못해 읽기 전용으로 전환했습니다. 브라우저 원본은 보존했습니다.');
      }
    };
    void bootstrap();
    return () => { cancelled = true; };
  }, [refreshHome, sidecarReady]);

  useEffect(() => {
    let cancelled = false;
    let isReady = false;
    const MAX_MS = 60_000;
    const FETCH_ABORT_MS = 1_500;
    const RETRY_MS = 500;
    const startMs = Date.now();

    const poll = async (): Promise<void> => {
      if (cancelled || isReady) return;
      setSidecarElapsed(Math.floor((Date.now() - startMs) / 1000));
      try {
        const ctrl = new AbortController();
        const abortHandle = setTimeout(() => ctrl.abort(), FETCH_ABORT_MS);
        const res = await fetch(`${SIDECAR_BASE}/health`, { signal: ctrl.signal });
        clearTimeout(abortHandle);
        if (!cancelled && res.ok) {
          isReady = true;
          setSidecarReady(true);
          // 엔진 버전 표시용. 파싱 실패해도 앱 흐름에는 영향 없음.
          try {
            const body = (await res.json()) as { version?: string };
            if (!cancelled && typeof body.version === 'string') {
              setEngineVersion(body.version);
            }
          } catch {
            // version 파싱 실패 — 헤더는 "엔진 –" 로 표시
          }
          return;
        }
      } catch {
        // sidecar not yet up — keep polling
      }
      if (!cancelled && !isReady && Date.now() - startMs < MAX_MS) {
        await new Promise<void>(r => setTimeout(r, RETRY_MS));
        return poll();
      } else if (!cancelled && !isReady) {
        setSidecarFailed(true);
      }
    };

    // Hard wall-clock guarantee: sidecarFailed set at exactly 60 s
    const failTimer = setTimeout(() => {
      if (!cancelled && !isReady) setSidecarFailed(true);
    }, MAX_MS);

    poll().finally(() => clearTimeout(failTimer));

    return () => {
      cancelled = true;
      clearTimeout(failTimer);
    };
  }, []);

  // 앱 버전: Tauri 런타임에서 getVersion() 조회. 비-Tauri(브라우저/테스트) 환경에서는
  // 실패하므로 빌드시 주입된 package.json version 폴백을 그대로 둔다.
  useEffect(() => {
    let cancelled = false;
    getVersion()
      .then(v => {
        if (!cancelled && v) setAppVersion(v);
      })
      .catch(() => {
        // 비-Tauri 환경 — __APP_VERSION__ 폴백 유지
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const activeConv = conversations.find(c => c.id === activeConvId) ?? null;
  const hasMessages = (activeConv?.messages?.length ?? 0) > 0 || pendingBot !== null;
  const activeMessageInventory = activeConvId
    ? messageInventories[activeConvId]
    : undefined;
  const activeMessageRecordCurrent = Boolean(
    activeConv
    && activeMessageInventory
    && activeMessageInventory.conversationId === activeConv.id
    && activeMessageInventory.conversationVersion === (activeConv.version ?? null)
    && activeMessageInventory.expectedCount === activeConv.message_count,
  );
  const activeMessageState = activeConv
    ? (
        activeMessageInventory?.status === 'COMPLETE'
        && !activeMessageRecordCurrent
          ? 'PARTIAL'
          : activeMessageInventory?.status ?? 'IDLE'
      )
    : undefined;
  const activeMessageIncomplete = Boolean(
    activeConv && !canMutateConversation(activeMessageInventory, {
      conversationId: activeConv.id,
      conversationVersion: activeConv.version ?? null,
      expectedCount: activeConv.message_count,
    }),
  );

  // --- Conversation management ---

  const createNewConversation = (): Conversation => {
    const now = new Date().toISOString();
    return {
      id: generateId(),
      title: '새 대화',
      title_is_custom: false,
      created_at: now,
      updated_at: now,
      messages: [],
    };
  };

  const handleNewConv = () => {
    messageLoadAbortRef.current?.abort();
    messageLoadGenerationRef.current += 1;
    setActiveConvId(null);
    setPendingBot(null);
    setCardMode('free');
    if (processing) {
      abortRef.current?.abort();
      setProcessing(false);
    }
  };

  const loadConversationInventory = useCallback(async (
    selected: Conversation,
    forceReload = false,
  ): Promise<boolean> => {
    const id = selected.id;
    const expectedCount = selected.message_count;
    const conversationVersion = selected.version ?? null;
    const cached = messageInventoriesRef.current[id];

    if (
      typeof expectedCount !== 'number'
      || !Number.isSafeInteger(expectedCount)
      || expectedCount < 0
    ) {
      messageLoadAbortRef.current?.abort();
      const generation = ++messageLoadGenerationRef.current;
      dispatchMessageInventory({
        type: 'LOAD_STARTED',
        id,
        conversationVersion,
        expectedCount: -1,
        messages: selected.messages,
        generation,
      });
      dispatchMessageInventory({
        type: 'INVALIDATE',
        id,
        generation,
        status: 'ERROR',
        reason: 'HOME_MESSAGE_COUNT_REQUIRED',
      });
      return false;
    }

    if (
      !forceReload
      && cached
      && cached.expectedCount === expectedCount
      && cached.conversationVersion === conversationVersion
      && canMutateConversation(cached, {
        conversationId: id,
        conversationVersion,
        expectedCount,
      })
    ) {
      const reassessment = assessMessageInventory(candidateFromRecord(cached, {
        conversationId: id,
        conversationVersion,
        generation: cached.generation,
      }));
      if (reassessment.status === 'COMPLETE' && reassessment.verified) {
        return true;
      }
    }

    messageLoadAbortRef.current?.abort();
    const controller = new AbortController();
    messageLoadAbortRef.current = controller;
    const generation = ++messageLoadGenerationRef.current;
    const resumableMessages = cached
      && forceReload
      && cached.conversationVersion === conversationVersion
      && cached.expectedCount === expectedCount
      && cached.messages.length <= expectedCount
      && new Set(cached.messages.map(item => item.id)).size === cached.messages.length
      && cached.messages.every((item, index) => item.sequence === index + 1)
      ? cached.messages
      : [];
    dispatchMessageInventory({
      type: 'LOAD_STARTED',
      id,
      conversationVersion,
      expectedCount,
      messages: resumableMessages,
      generation,
    });

    const result = await fetchConversationMessages(id, expectedCount, {
      signal: controller.signal,
      initialItems: resumableMessages,
      conversationVersion,
    }).catch(() => null);
    if (
      generation !== messageLoadGenerationRef.current
      || controller.signal.aborted
    ) return false;
    if (result === null) {
      dispatchMessageInventory({
        type: 'INVALIDATE',
        id,
        generation,
        status: 'ERROR',
        reason: 'HOME_MESSAGE_PAGE_FAILED',
      });
      return false;
    }

    setConversations(previous => previous.map(conversation => (
      conversation.id === id ? { ...conversation, messages: result.messages } : conversation
    )));

    if (result.status === 'ERROR') {
      dispatchMessageInventory({
        type: 'INVALIDATE',
        id,
        generation,
        status: 'ERROR',
        reason: result.error_code ?? 'HOME_MESSAGE_PAGE_FAILED',
        messages: result.messages,
        nextSequence: result.next_sequence,
        partialErrorCount: result.partial_errors.length,
      });
      return false;
    }

    const candidate = {
      conversationId: result.conversation_id,
      conversationVersion: result.conversation_version,
      currentConversationId: id,
      currentConversationVersion: conversationVersion,
      expectedCount,
      messages: result.messages,
      nextSequence: result.next_sequence,
      partialErrors: result.partial_errors,
      locked: result.locked,
      generation,
      currentGeneration: messageLoadGenerationRef.current,
    };
    const assessment = assessMessageInventory(candidate);
    dispatchMessageInventory({
      type: 'LOAD_ASSESSED',
      id,
      generation,
      candidate,
    });
    return assessment.status === 'COMPLETE' && assessment.verified;
  }, []);

  const handleSelectConv = async (id: string, forceReload = false) => {
    if (processing) {
      abortRef.current?.abort();
      setProcessing(false);
    }
    setPendingBot(null);
    setActiveConvId(id);
    const selected = conversationsRef.current.find(conversation => conversation.id === id);
    if (!selected) return;
    await loadConversationInventory(selected, forceReload);
  };

  const ensureConversationMutationAllowed = async (
    conversation: Conversation,
  ): Promise<boolean> => {
    if (homeReadOnly) return false;
    const cached = messageInventoriesRef.current[conversation.id];
    if (
      canMutateConversation(cached, {
        conversationId: conversation.id,
        conversationVersion: conversation.version ?? null,
        expectedCount: conversation.message_count,
      })
    ) {
      return true;
    }
    const verified = await loadConversationInventory(conversation);
    if (!verified) {
      setHomeStoreError(
        '대화 내용을 완전히 검증하지 못해 변경 작업을 차단했습니다.',
      );
    }
    return verified;
  };

  const handleRename = (id: string, title: string) => {
    const target = conversationsRef.current.find(conversation => conversation.id === id);
    if (!target) return;
    void (async () => {
      if (!await ensureConversationMutationAllowed(target)) return;
      setConversations(previous => previous.map(conversation => conversation.id === id ? { ...conversation, title, title_is_custom: true } : conversation));
      await queueRef.current.enqueue(id, async () => {
        try {
          const result = await renameConversation(target, title);
          setConversations(previous => previous.map(conversation => conversation.id === id ? { ...conversation, ...result } : conversation));
        } catch (error) {
          await reportMutationFailure(error, '대화 이름을');
        }
      });
    })();
  };

  const handleDeleteRequest = (id: string) => {
    setDeleteTarget(id);
  };

  const handleDeleteConfirm = () => {
    if (!deleteTarget) return;
    const id = deleteTarget;
    const target = conversationsRef.current.find(conversation => conversation.id === id);
    setDeleteTarget(null);
    if (!target) return;
    void (async () => {
      if (!await ensureConversationMutationAllowed(target)) return;
      await queueRef.current.enqueue(id, async () => {
        try {
          const result = await trashConversation(target);
          setConversations(previous => previous.filter(conversation => conversation.id !== id));
          setTrashedConversations(previous => [{ ...target, ...result }, ...previous]);
          dispatchMessageInventory({ type: 'REMOVE', id });
        } catch (error) {
          await reportMutationFailure(error, '대화를 휴지통에');
        }
      });
      if (activeConvId === id) {
        setActiveConvId(null);
        setPendingBot(null);
      }
    })();
  };

  const handleCreateFolder = (name: string, parentId: string | null) => {
    if (homeReadOnly) return;
    void queueRef.current.enqueue('folders', async () => {
      try {
        const folder = await createFolder(name, parentId);
        setFolders(previous => [...previous, folder]);
      } catch (error) {
        await reportMutationFailure(error, '폴더를');
      }
    });
  };

  const handleRenameFolder = (folder: FolderRecord, name: string) => {
    if (homeReadOnly) return;
    void queueRef.current.enqueue('folders', async () => {
      try {
        const result = await renameFolder(folder, name);
        setFolders(previous => previous.map(item => item.folder_id === folder.folder_id ? result : item));
      } catch (error) {
        await reportMutationFailure(error, '폴더 이름을');
      }
    });
  };

  const handleDeleteFolder = (folder: FolderRecord) => {
    if (homeReadOnly || !window.confirm(`‘${folder.display_name}’ 폴더를 삭제하시겠습니까? 비어 있는 폴더만 삭제됩니다.`)) return;
    void queueRef.current.enqueue('folders', async () => {
      try {
        await deleteFolder(folder);
        setFolders(previous => previous.filter(item => item.folder_id !== folder.folder_id));
      } catch (error) {
        await reportMutationFailure(error, '폴더를');
      }
    });
  };

  const handleMove = (conversation: Conversation, folderId: string) => {
    if (conversation.folder_id === folderId) return;
    void (async () => {
      if (!await ensureConversationMutationAllowed(conversation)) return;
      setConversations(previous => previous.map(item => item.id === conversation.id ? { ...item, folder_id: folderId } : item));
      await queueRef.current.enqueue(conversation.id, async () => {
        try {
          const result = await moveConversation(conversation, folderId);
          setConversations(previous => previous.map(item => item.id === conversation.id ? { ...item, ...result } : item));
        } catch (error) {
          await reportMutationFailure(error, '대화 위치를');
        }
      });
    })();
  };

  const handleRestore = (conversation: Conversation) => {
    void (async () => {
      if (!await ensureConversationMutationAllowed(conversation)) return;
      await queueRef.current.enqueue(conversation.id, async () => {
        try {
          const result = await restoreConversation(conversation);
          setTrashedConversations(previous => previous.filter(item => item.id !== conversation.id));
          setConversations(previous => [{ ...conversation, ...result, deleted_at: null }, ...previous]);
          dispatchMessageInventory({ type: 'REMOVE', id: conversation.id });
        } catch (error) {
          await reportMutationFailure(error, '대화를');
        }
      });
    })();
  };

  const handlePermanentDelete = (conversation: Conversation) => {
    if (!window.confirm(`‘${conversation.title}’ 대화를 영구 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.`)) return;
    void (async () => {
      if (!await ensureConversationMutationAllowed(conversation)) return;
      await queueRef.current.enqueue(conversation.id, async () => {
        try {
          await permanentlyDeleteConversation(conversation);
          setTrashedConversations(previous => previous.filter(item => item.id !== conversation.id));
          dispatchMessageInventory({ type: 'REMOVE', id: conversation.id });
        } catch (error) {
          await reportMutationFailure(error, '대화를 영구');
        }
      });
    })();
  };

  const handleSearch = (query: string) => {
    const value = query.trim();
    window.clearTimeout(searchTimerRef.current);
    searchTimerRef.current = window.setTimeout(() => {
      if (!value) {
        void refreshHome().catch(() => setHomeReadOnly(true));
        return;
      }
      void searchConversations(value)
        .then(results => setConversations(mergeLoadedMessages(results)))
        .catch(error => reportMutationFailure(error, '검색 결과를'));
    }, 200);
  };

  const handleSettingsAction=(action:SettingsAction)=>{setSettingsOpen(false);if(action==='policy')setAdminPolicyConsoleOpen(true);else if(action==='format')setCompanyFormatConsoleOpen(true);else if(action==='fact')setCompanyFactConsoleOpen(true);else if(action==='learning')setCompanyLearningConsoleOpen(true);else if(action==='accounting')setAccountingModalOpen(true);else setEgressMonitorOpen(true);};

  const handleDeleteCancel = () => {
    const target = deleteTarget;
    setDeleteTarget(null);
    if (target) {
      window.setTimeout(() => {
        Array.from(document.querySelectorAll<HTMLButtonElement>('[data-conversation-menu]'))
          .find(button => button.dataset.conversationMenu === target)
          ?.focus();
      }, 0);
    }
  };

  // --- Submit handler ---

  const handleSubmit = async (text: string, files: File[], mode: string): Promise<boolean> => {
    if (homeReadOnly || homeLoading) {
      setHomeStoreError('저장소가 준비되지 않아 전송하지 않았습니다. 입력 내용은 그대로 유지됩니다.');
      return false;
    }
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    let currentSource: 'factpack' | 'llm' | null = null;
    const original = activeConvId
      ? conversationsRef.current.find(conversation => conversation.id === activeConvId) ?? createNewConversation()
      : createNewConversation();
    if (
      activeConvId
      && !canMutateConversation(messageInventoriesRef.current[activeConvId], {
        conversationId: original.id,
        conversationVersion: original.version ?? null,
        expectedCount: original.message_count,
      })
    ) {
      setHomeStoreError('기존 대화를 빠짐없이 복원하기 전에는 새 메시지를 전송할 수 없습니다.');
      return false;
    }
    const now = new Date().toISOString();
    const userMessage: Message = { id: generateId(), role: 'user', content: text, timestamp: now };
    const isFirstMessage = (original.message_count ?? original.messages.length) === 0;
    const command: Conversation = {
      ...original,
      title: isFirstMessage && !original.title_is_custom ? text.slice(0, 40) || '첨부 파일 대화' : original.title,
      updated_at: now,
    };

    let acceptedConversation: Conversation;
    let accepted: TurnCorrelation;
    try {
      accepted = await queueRef.current.enqueue(command.id, () => acceptUserTurn(command, userMessage));
      acceptedConversation = {
        ...command,
        ...accepted,
        messages: [...original.messages, userMessage],
        message_count: (original.message_count ?? original.messages.length) + 1,
      };
      setConversations(previous => previous.some(conversation => conversation.id === command.id)
        ? previous.map(conversation => conversation.id === command.id ? acceptedConversation : conversation)
        : [acceptedConversation, ...previous]);
      setActiveConvId(command.id);
      messageLoadAbortRef.current?.abort();
      const generation = ++messageLoadGenerationRef.current;
      dispatchMessageInventory({
        type: 'LOAD_STARTED',
        id: command.id,
        conversationVersion: acceptedConversation.version ?? null,
        expectedCount: acceptedConversation.message_count
          ?? acceptedConversation.messages.length,
        messages: acceptedConversation.messages,
        generation,
      });
    } catch (error) {
      await reportMutationFailure(error, '사용자 요청을');
      return false;
    }

    processingConversationRef.current = command.id;
    setPendingBot({ source: null, loadingStatus: '답변 준비 중...', streamBuffer: '', content: null, isError: false });
    setProcessing(true);

    const recordFailure = async (state: 'FAILED' | 'CANCELLED' | 'TIMED_OUT', code: string) => {
      try {
        await queueRef.current.enqueue(command.id, () => recordTerminal(accepted, state, code));
      } catch {
        setHomeStoreError('작업 종료 상태를 감사 로그에 기록하지 못했습니다.');
      }
    };

    try {
      const formData = new FormData();
      formData.append('query', text);
      formData.append('card_mode', sidecarCardMode(mode || 'free'));
      formData.append('total_chunks', '1');
      files.forEach((file, index) => formData.append(`file_${index}`, file));
      formData.append('file_count', String(files.length));
      const response = await sidecarFetch('/api/analyze/stream', { method: 'POST', body: formData, signal: ctrl.signal });
      if (!response.ok) throw new Error(`SIDECAR_HTTP_${response.status}`);
      const reader = response.body?.getReader();
      if (!reader) throw new Error('SIDECAR_STREAM_MISSING');
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (ctrl.signal.aborted) throw new DOMException('Aborted', 'AbortError');
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const blocks = buffer.split('\n\n');
        buffer = blocks.pop() ?? '';
        for (const block of blocks) {
          const lines = block.split('\n');
          const eventType = (lines.find(line => line.startsWith('event:'))?.slice(6).trim() ?? 'unknown') as SSEEvent['type'];
          const dataLine = lines.find(line => line.startsWith('data:'));
          if (!dataLine) continue;
          let data: Record<string, unknown>;
          try { data = JSON.parse(dataLine.slice(5).trim()) as Record<string, unknown>; } catch { continue; }

          if (eventType === 'meta') {
            currentSource = (data.source as 'factpack' | 'llm' | undefined) ?? null;
            setPendingBot(previous => previous ? { ...previous, source: currentSource } : previous);
          } else if (eventType === 'chunk') {
            setPendingBot(previous => previous ? { ...previous, streamBuffer: previous.streamBuffer + String(data.token ?? '') } : previous);
          } else if (eventType === 'phase_start' || eventType === 'chunk_progress' || eventType === 'reduce_start' || eventType === 'verify_start') {
            const current = Number(data.current ?? 0);
            const total = Math.max(1, Number(data.total ?? 1));
            const progressPercent = eventType === 'phase_start' ? 5 : eventType === 'chunk_progress' ? 5 + Math.round((current / total) * 65) : eventType === 'reduce_start' ? 85 : 95;
            flushSync(() => setPendingBot(previous => previous ? { ...previous, loadingStatus: String(data.status_message ?? '처리 중'), progressPercent } : previous));
          } else if (eventType === 'complete') {
            const botMessage: Message = {
              id: generateId(), role: 'butler', content: String(data.result_text ?? ''),
              timestamp: new Date().toISOString(), source: currentSource ?? undefined,
            };
            const persisted = await queueRef.current.enqueue(command.id, () => appendAssistantTurn(acceptedConversation, botMessage, accepted));
            const completedConversation: Conversation = {
              ...acceptedConversation,
              ...persisted,
              messages: [...acceptedConversation.messages, botMessage],
              message_count: (acceptedConversation.message_count
                ?? acceptedConversation.messages.length) + 1,
            };
            setConversations(previous => previous.map(conversation => (
              conversation.id === command.id
                ? completedConversation
                : conversation
            )));
            if (!await loadConversationInventory(completedConversation, true)) {
              setHomeStoreError(
                '저장된 대화의 전체 메시지를 검증하지 못해 추가 전송을 차단했습니다.',
              );
            }
            setPendingBot(null);
            setProcessing(false);
            processingConversationRef.current = null;
            return true;
          } else if (eventType === 'cancelled') {
            const reason = String(data.reason ?? 'USER_CANCEL');
            const timedOut = reason.includes('timeout');
            await recordFailure(timedOut ? 'TIMED_OUT' : 'CANCELLED', timedOut ? 'MODEL_TIMEOUT' : 'USER_CANCEL');
            await loadConversationInventory(acceptedConversation, true);
            setPendingBot(previous => previous ? { ...previous, content: timedOut ? '처리 시간이 초과되어 중단됐습니다.' : '작업이 중단됐습니다.', isError: true, loadingStatus: '', streamBuffer: '' } : previous);
            setProcessing(false);
            processingConversationRef.current = null;
            return true;
          } else if (eventType === 'error') {
            await recordFailure('FAILED', 'MODEL_STREAM_ERROR');
            await loadConversationInventory(acceptedConversation, true);
            setPendingBot(previous => previous ? { ...previous, content: String(data.message ?? '처리 중 오류가 발생했습니다.'), isError: true, loadingStatus: '', streamBuffer: '' } : previous);
            setProcessing(false);
            processingConversationRef.current = null;
            return true;
          }
        }
      }
      throw new Error('MODEL_STREAM_INCOMPLETE');
    } catch (error: unknown) {
      const aborted = typeof error === 'object' && error !== null && 'name' in error && error.name === 'AbortError';
      await recordFailure(aborted ? 'CANCELLED' : 'FAILED', aborted ? 'USER_CANCEL' : 'MODEL_REQUEST_FAILED');
      await loadConversationInventory(acceptedConversation, true);
      setPendingBot(previous => previous ? {
        ...previous,
        content: aborted ? '작업이 중단됐습니다.' : uiSafeSidecarErrorMessage(error),
        isError: true,
        loadingStatus: '',
        streamBuffer: '',
      } : previous);
      setProcessing(false);
      processingConversationRef.current = null;
      return true;
    }
  };

  const handleStop = () => {
    abortRef.current?.abort();
  };

  const closeAllCardModals = () => {
    setAccountingModalOpen(false);
    setRequestParsingModalOpen(false);
    setDocumentTransformModalOpen(false);
    setBox3DraftModalOpen(false);
    setFormFillModalOpen(false);
    setDocumentReviewModalOpen(false);
  };

  const handleCardSelect = (mode: string | null) => {
    const m = mode ?? 'free';
    setCardMode(m);
    closeAllCardModals();
    if (m === 'accounting_classify') {
      setAccountingModalOpen(true);
    } else if (m === 'request_organize') {
      setRequestParsingModalOpen(true);
    } else if (m === 'format_convert') {
      setDocumentTransformModalOpen(true);
    } else if (m === 'new_draft') {
      setBox3DraftModalOpen(true);
    } else if (m === 'form_fill') {
      setFormFillModalOpen(true);
    } else if (m === 'document_review') {
      setDocumentReviewModalOpen(true);
    }
  };

  const closeEgressMonitor = useCallback(() => {
    setEgressMonitorOpen(false);
    window.requestAnimationFrame(() => egressBadgeRef.current?.focus());
  }, []);

  return (
    <div style={{ display: 'flex', height: '100%', background: 'var(--color-bg-app)' }}>
      <Sidebar
        conversations={conversations}
        trashedConversations={trashedConversations}
        folders={folders}
        activeConvId={activeConvId}
        onSelect={handleSelectConv}
        onNew={handleNewConv}
        onRename={handleRename}
        onDeleteRequest={handleDeleteRequest}
        onCreateFolder={handleCreateFolder}
        onRenameFolder={handleRenameFolder}
        onDeleteFolder={handleDeleteFolder}
        onMove={handleMove}
        onRestore={handleRestore}
        onPermanentDelete={handlePermanentDelete}
        onOpenSettings={()=>setSettingsOpen(true)}
        onRetry={() => { setHomeLoading(true); void refreshHome().catch(() => { setHomeLoading(false); setHomeReadOnly(true); }); }}
        onSearch={handleSearch}
        disabled={homeReadOnly || processing}
        isOpen={sidebarOpen}
      />

      <main
        className="home-main"
        style={{
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          minWidth: 0,
        }}
      >
        {/* Top bar */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            padding: 'var(--space-3) var(--space-4)',
            borderBottom: '1px solid var(--color-border-subtle)',
            background: 'var(--color-bg-input)',
            gap: 'var(--space-3)',
          }}
        >
          <button
            data-testid="sidebar-toggle-btn"
            onClick={() => setSidebarOpen(o => !o)}
            style={{
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              fontSize: 18,
              color: 'var(--color-text-secondary)',
              padding: '2px 4px',
              borderRadius: 4,
            }}
            aria-label="사이드바 토글"
          >
            ☰
          </button>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <img
              src={butlerIconStaticUrl}
              width={24}
              height={24}
              alt=""
              data-testid="butler-header-icon"
            />
            <span
              style={{
                fontSize: 'var(--text-base)',
                fontWeight: 600,
                color: 'var(--color-brand-primary)',
              }}
            >
              Butler
            </span>
            <span
              data-testid="app-version-info"
              title="앱 버전 · 빌드(브랜치 커밋) · 엔진 버전"
              style={{
                fontSize: 'var(--text-xs)',
                color: 'var(--color-text-secondary)',
                opacity: 0.7,
                whiteSpace: 'nowrap',
              }}
            >
              v{appVersion} · {__BUILD_BRANCH__} {__BUILD_COMMIT__} · 엔진 {engineVersion ?? '–'}
            </span>
          </div>
          <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
            <EgressBadge
              ref={egressBadgeRef}
              state={egressState}
              onOpenDetails={() => setEgressMonitorOpen(true)}
            />
          </div>
        </div>

        <div className="home-status-rail" data-testid="home-status-rail">
          {homeInventoryState !== 'COMPLETE' && (
            <div className="home-inventory-status" role="status" data-state={homeInventoryState}>
              {homeInventoryState === 'LOADING'
                ? '전체 대화 목록을 복원하고 있습니다.'
                : '대화 목록이 불완전하여 저장과 전송을 차단했습니다.'}
              {homeInventoryState === 'PARTIAL' && (
                <button onClick={() => { setHomeLoading(true); void refreshHome(); }}>목록 다시 불러오기</button>
              )}
            </div>
          )}
          {activeConvId && activeMessageState && activeMessageState !== 'COMPLETE' && (
            <div className="home-inventory-status" role="status" data-state={activeMessageState}>
              {activeMessageState === 'LOADING'
                ? '대화 내용을 빠짐없이 복원하고 있습니다.'
                : activeMessageState === 'LOCKED'
                  ? '암호화 키를 확인할 수 없어 대화 내용이 잠겼습니다.'
                  : '대화 내용 일부를 복원하지 못했습니다. 현재까지 복원된 내용은 보존했습니다.'}
              {activeMessageState !== 'LOADING' && activeMessageState !== 'LOCKED' && (
                <button onClick={() => { void handleSelectConv(activeConvId, true); }}>
                  이어서 다시 불러오기
                </button>
              )}
              {(activeMessageRecordCurrent
                ? activeMessageInventory?.errorCode
                : 'HOME_MESSAGE_INVENTORY_STALE') && (
                <span className="home-inventory-code">
                  {activeMessageRecordCurrent
                    ? activeMessageInventory?.errorCode
                    : 'HOME_MESSAGE_INVENTORY_STALE'}
                </span>
              )}
            </div>
          )}
          <SetupBanner
            setup={setupUiState}
            onStart={() => setAccountingModalOpen(true)}
          />
        </div>

        {/* Content area — card grid always visible; compact strip when messages present */}
        {hasMessages ? (
          <>
            <CardGrid compact onCardSelect={handleCardSelect} />
            <MessageList
              messages={activeConv?.messages ?? []}
              pendingBot={pendingBot}
              onRetry={() => {
                setPendingBot(null);
              }}
            />
          </>
        ) : (
          <div className="home-empty-content">
            <CardGrid onCardSelect={handleCardSelect} />
          </div>
        )}

        <ChatInput
          onSubmit={handleSubmit}
          onStop={handleStop}
          processing={processing}
          cardMode={cardMode}
          disabled={homeReadOnly || homeLoading || activeMessageIncomplete}
        />
      </main>

      {deleteTarget && (
        <DeleteConfirmModal
          isOpen={true}
          onConfirm={handleDeleteConfirm}
          onCancel={handleDeleteCancel}
        />
      )}

      <Suspense fallback={<div className="modal-loading" role="status">기능을 불러오는 중입니다.</div>}>
      {egressMonitorOpen && (
        <EgressMonitor
          state={egressState}
          onRefresh={() => { void refreshEgress(); }}
          onClose={closeEgressMonitor}
        />
      )}
      {settingsOpen&&<SettingsShell onClose={()=>setSettingsOpen(false)} onAction={handleSettingsAction} appVersion={appVersion} engineVersion={engineVersion}/>}
      {homeStoreError&&<div className="home-store-error" role="alert" data-home-startup={homeStartup?.status ?? 'UNKNOWN'}><span>{homeStoreError}</span><button onClick={()=>setHomeStoreError(null)}>닫기</button></div>}

      {accountingModalOpen && (
        <AccountingModal
          onClose={() => {
            setAccountingModalOpen(false);
            setCardMode('free');
          }}
        />
      )}

      {requestParsingModalOpen && (
        <RequestParsingModal
          onClose={() => {
            setRequestParsingModalOpen(false);
            setCardMode('free');
          }}
        />
      )}

      {documentTransformModalOpen && (
        <Card2DocumentTransform
          onClose={() => {
            setDocumentTransformModalOpen(false);
            setCardMode('free');
          }}
        />
      )}
      {box3DraftModalOpen && (
        <Box3DraftModal
          onClose={() => {
            setBox3DraftModalOpen(false);
            setCardMode('free');
          }}
        />
      )}
      {formFillModalOpen && (
        <FormFillModal
          onClose={() => {
            setFormFillModalOpen(false);
            setCardMode('free');
          }}
        />
      )}
      {documentReviewModalOpen && (
        <DocumentReviewModal
          onClose={() => {
            setDocumentReviewModalOpen(false);
            setCardMode('free');
          }}
        />
      )}
      {adminPolicyConsoleOpen && (
        <AdminPolicyConsole onClose={() => setAdminPolicyConsoleOpen(false)} />
      )}
      {companyFormatConsoleOpen && (
        <CompanyFormatConsole onClose={() => setCompanyFormatConsoleOpen(false)} />
      )}
      {companyFactConsoleOpen && (
        <CompanyFactApprovalConsole onClose={() => setCompanyFactConsoleOpen(false)} />
      )}
      {companyLearningConsoleOpen && (
        <CompanyLearningConsole onClose={() => setCompanyLearningConsoleOpen(false)} />
      )}
      </Suspense>
      {conflictNotice && <div className="home-conflict-notice" role="alert"><span>{conflictNotice}</span><button onClick={() => setConflictNotice(null)}>확인</button></div>}
      {/* Sidecar readiness overlay */}
      {!sidecarReady && !sidecarFailed && (
        <div
          data-testid="sidecar-loading"
          style={{
            position: 'fixed', inset: 0, zIndex: 9999,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            background: 'var(--color-bg-app)',
          }}
        >
          <div style={{ textAlign: 'center', padding: '40px 32px' }}>
            <p style={{ fontSize: 40, margin: '0 0 16px' }}>⚙️</p>
            <h2 style={{ margin: '0 0 8px', fontSize: 18 }}>분석 엔진 시작 중</h2>
            <p data-testid="sidecar-elapsed" style={{ color: 'var(--color-text-secondary)', fontSize: 14, margin: 0 }}>
              {sidecarElapsed}초 경과 / 최대 60초
            </p>
          </div>
        </div>
      )}
      {!sidecarReady && sidecarFailed && (
        <div
          data-testid="sidecar-failed"
          style={{
            position: 'fixed', inset: 0, zIndex: 9999,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            background: 'var(--color-bg-app)',
          }}
        >
          <div style={{ textAlign: 'center', padding: '40px 32px', maxWidth: 400 }}>
            <p style={{ fontSize: 32, margin: '0 0 16px' }}>⚠️</p>
            <h2 style={{ margin: '0 0 8px', fontSize: 18 }}>분석 엔진 연결 실패</h2>
            <p style={{ color: 'var(--color-text-secondary)', fontSize: 14, margin: 0 }}>
              60초 동안 응답이 없습니다. Butler.app을 재실행해주세요.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
