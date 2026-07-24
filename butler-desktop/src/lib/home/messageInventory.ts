import type { Message } from '../../types';

export type MessageInventoryStatus =
  | 'IDLE'
  | 'LOADING'
  | 'COMPLETE'
  | 'PARTIAL'
  | 'ERROR'
  | 'LOCKED';

export type InventoryPartialError = Readonly<{
  sequence: number;
  code: string;
}>;

export type InventoryCandidate = {
  conversationId: string;
  conversationVersion: number | null;
  currentConversationId: string;
  currentConversationVersion: number | null;
  expectedCount: number;
  messages: Message[];
  nextSequence: number | null;
  partialErrors: ReadonlyArray<InventoryPartialError>;
  locked: boolean;
  generation: number;
  currentGeneration: number;
};

export type InventoryAssessment =
  | { status: 'COMPLETE'; verified: true; errorCode: null }
  | {
      status: 'PARTIAL' | 'ERROR' | 'LOCKED';
      verified: false;
      errorCode: string;
    };

export type MessageInventoryRecord = {
  status: MessageInventoryStatus;
  conversationId: string;
  conversationVersion: number | null;
  expectedCount: number;
  messages: Message[];
  nextSequence: number | null;
  partialErrorCount: number;
  errorCode: string | null;
  generation: number;
  verified: boolean;
};

export type MessageInventoryMap = Readonly<
  Record<string, MessageInventoryRecord>
>;

export type InventoryAction =
  | {
      type: 'LOAD_STARTED';
      id: string;
      conversationVersion: number | null;
      expectedCount: number;
      messages: Message[];
      generation: number;
    }
  | {
      type: 'LOAD_ASSESSED';
      id: string;
      generation: number;
      candidate: InventoryCandidate;
    }
  | {
      type: 'INVALIDATE';
      id: string;
      generation: number;
      status: 'PARTIAL' | 'ERROR' | 'LOCKED';
      reason: string;
      messages?: Message[];
      nextSequence?: number | null;
      partialErrorCount?: number;
    }
  | { type: 'REMOVE'; id: string };

const blocked = (
  status: 'PARTIAL' | 'ERROR' | 'LOCKED',
  errorCode: string,
): InventoryAssessment => ({ status, verified: false, errorCode });

/**
 * The single authority that may issue a verified COMPLETE assessment.
 *
 * This function intentionally examines metadata only. Message bodies are
 * neither hashed nor logged. Complexity is O(N) time and O(N) message IDs.
 */
export function assessMessageInventory(
  candidate: InventoryCandidate,
): InventoryAssessment {
  if (candidate.locked) {
    return blocked('LOCKED', 'HOME_STORE_LOCKED');
  }
  if (candidate.partialErrors.length > 0) {
    const first = candidate.partialErrors[0];
    return blocked(
      'PARTIAL',
      typeof first?.code === 'string' && first.code.length > 0
        ? first.code
        : 'HOME_MESSAGE_PARTIAL_ERROR',
    );
  }
  if (
    !Number.isSafeInteger(candidate.expectedCount)
    || candidate.expectedCount < 0
  ) {
    return blocked('ERROR', 'HOME_MESSAGE_COUNT_REQUIRED');
  }
  if (candidate.messages.length !== candidate.expectedCount) {
    return blocked('PARTIAL', 'HOME_MESSAGE_COUNT_MISMATCH');
  }

  const ids = new Set<string>();
  for (let index = 0; index < candidate.messages.length; index += 1) {
    const message = candidate.messages[index];
    if (
      !message
      || !Number.isSafeInteger(message.sequence)
      || message.sequence !== index + 1
    ) {
      return blocked('PARTIAL', 'HOME_MESSAGE_SEQUENCE_GAP');
    }
    if (
      typeof message.id !== 'string'
      || message.id.length === 0
      || ids.has(message.id)
    ) {
      return blocked('PARTIAL', 'HOME_MESSAGE_ID_DUPLICATE');
    }
    ids.add(message.id);
  }
  if (candidate.nextSequence !== null) {
    return blocked('PARTIAL', 'HOME_MESSAGE_INVENTORY_INCOMPLETE');
  }
  if (
    candidate.conversationId !== candidate.currentConversationId
    || candidate.conversationVersion !== candidate.currentConversationVersion
    || candidate.generation !== candidate.currentGeneration
  ) {
    return blocked('PARTIAL', 'HOME_MESSAGE_INVENTORY_STALE');
  }
  return { status: 'COMPLETE', verified: true, errorCode: null };
}

export function messageInventoryReducer(
  state: MessageInventoryMap,
  action: InventoryAction,
): MessageInventoryMap {
  if (action.type === 'REMOVE') {
    if (!(action.id in state)) return state;
    const next = { ...state };
    delete next[action.id];
    return next;
  }

  if (action.type === 'LOAD_STARTED') {
    return {
      ...state,
      [action.id]: {
        status: 'LOADING',
        conversationId: action.id,
        conversationVersion: action.conversationVersion,
        expectedCount: action.expectedCount,
        messages: action.messages,
        nextSequence: action.messages.at(-1)?.sequence ?? null,
        partialErrorCount: 0,
        errorCode: null,
        generation: action.generation,
        verified: false,
      },
    };
  }

  const current = state[action.id];
  if (!current || current.generation !== action.generation) {
    return state;
  }

  if (action.type === 'INVALIDATE') {
    return {
      ...state,
      [action.id]: {
        ...current,
        status: action.status,
        messages: action.messages ?? current.messages,
        nextSequence: 'nextSequence' in action
          ? action.nextSequence ?? null
          : current.nextSequence,
        partialErrorCount:
          action.partialErrorCount ?? current.partialErrorCount,
        errorCode: action.reason,
        verified: false,
      },
    };
  }

  if (action.candidate.generation !== action.generation) {
    return state;
  }
  const assessment = assessMessageInventory(action.candidate);

  return {
    ...state,
    [action.id]: {
      status: assessment.status,
      conversationId: action.candidate.conversationId,
      conversationVersion: action.candidate.conversationVersion,
      expectedCount: action.candidate.expectedCount,
      messages: action.candidate.messages,
      nextSequence: action.candidate.nextSequence,
      partialErrorCount: action.candidate.partialErrors.length,
      errorCode: assessment.errorCode,
      generation: action.generation,
      verified: assessment.verified,
    },
  };
}

export const canMutateConversation = (
  record: MessageInventoryRecord | undefined,
  current?: {
    conversationId: string;
    conversationVersion: number | null;
    expectedCount: number | undefined;
  },
): boolean =>
  record?.status === 'COMPLETE'
  && record.verified === true
  && record.errorCode === null
  && (
    current === undefined
    || (
      record.conversationId === current.conversationId
      && record.conversationVersion === current.conversationVersion
      && record.expectedCount === current.expectedCount
    )
  );

export function candidateFromRecord(
  record: MessageInventoryRecord,
  current: {
    conversationId: string;
    conversationVersion: number | null;
    generation: number;
  },
): InventoryCandidate {
  return {
    conversationId: record.conversationId,
    conversationVersion: record.conversationVersion,
    currentConversationId: current.conversationId,
    currentConversationVersion: current.conversationVersion,
    expectedCount: record.expectedCount,
    messages: record.messages,
    nextSequence: record.nextSequence,
    partialErrors: record.partialErrorCount === 0
      ? []
      : [{ sequence: 0, code: record.errorCode ?? 'HOME_MESSAGE_PARTIAL_ERROR' }],
    locked: record.status === 'LOCKED',
    generation: record.generation,
    currentGeneration: current.generation,
  };
}
