import { describe, expect, it } from 'vitest';

import type { Message } from '../../types';
import {
  assessMessageInventory,
  canMutateConversation,
  messageInventoryReducer,
  type InventoryCandidate,
  type MessageInventoryMap,
} from './messageInventory';

const VERSION = 11;
const GENERATION = 19;

function message(sequence: number, id = `message-${sequence}`): Message {
  return {
    id,
    role: sequence % 2 === 0 ? 'butler' : 'user',
    content: 'not inspected by inventory validation',
    timestamp: '2026-07-24T00:00:00Z',
    sequence,
  };
}

function candidate(
  expectedCount: number,
  messages = Array.from(
    { length: Math.max(0, expectedCount) },
    (_, index) => message(index + 1),
  ),
  patch: Partial<InventoryCandidate> = {},
): InventoryCandidate {
  return {
    conversationId: 'conversation-1',
    conversationVersion: VERSION,
    currentConversationId: 'conversation-1',
    currentConversationVersion: VERSION,
    expectedCount,
    messages,
    nextSequence: null,
    partialErrors: [],
    locked: false,
    generation: GENERATION,
    currentGeneration: GENERATION,
    ...patch,
  };
}

describe('message inventory single authority', () => {
  it.each([0, 1, 2, 100, 101, 1000])(
    'issues a verified assessment only for exact contiguous inventory %i',
    count => {
      expect(assessMessageInventory(candidate(count))).toEqual({
        status: 'COMPLETE',
        verified: true,
        errorCode: null,
      });
    },
  );

  it.each([
    {
      name: 'starts at sequence 2 with count equality',
      value: candidate(2, [message(2), message(3)]),
      status: 'PARTIAL',
      code: 'HOME_MESSAGE_SEQUENCE_GAP',
    },
    {
      name: 'has a middle gap',
      value: candidate(2, [message(1), message(3)]),
      status: 'PARTIAL',
      code: 'HOME_MESSAGE_SEQUENCE_GAP',
    },
    {
      name: 'has a duplicate sequence',
      value: candidate(2, [message(1), message(1, 'message-2')]),
      status: 'PARTIAL',
      code: 'HOME_MESSAGE_SEQUENCE_GAP',
    },
    {
      name: 'has a duplicate message id',
      value: candidate(2, [message(1, 'same'), message(2, 'same')]),
      status: 'PARTIAL',
      code: 'HOME_MESSAGE_ID_DUPLICATE',
    },
    {
      name: 'has a structured partial error',
      value: candidate(2, undefined, {
        partialErrors: [{ sequence: 2, code: 'HOME_MESSAGE_UNREADABLE' }],
      }),
      status: 'PARTIAL',
      code: 'HOME_MESSAGE_UNREADABLE',
    },
    {
      name: 'has a non-terminal cursor',
      value: candidate(2, undefined, { nextSequence: 2 }),
      status: 'PARTIAL',
      code: 'HOME_MESSAGE_INVENTORY_INCOMPLETE',
    },
    {
      name: 'is locked',
      value: candidate(2, undefined, { locked: true }),
      status: 'LOCKED',
      code: 'HOME_STORE_LOCKED',
    },
    {
      name: 'has an invalid expected count',
      value: candidate(Number.NaN, []),
      status: 'ERROR',
      code: 'HOME_MESSAGE_COUNT_REQUIRED',
    },
    {
      name: 'has the audited null conversation version',
      value: candidate(2, undefined, {
        conversationVersion: null,
        currentConversationVersion: null,
      }),
      status: 'PARTIAL',
      code: 'HOME_CONVERSATION_VERSION_REQUIRED',
    },
    {
      name: 'has a zero conversation version',
      value: candidate(2, undefined, {
        conversationVersion: 0,
        currentConversationVersion: 0,
      }),
      status: 'PARTIAL',
      code: 'HOME_CONVERSATION_VERSION_REQUIRED',
    },
    {
      name: 'has the audited zero load generation',
      value: candidate(2, undefined, {
        generation: 0,
        currentGeneration: 0,
      }),
      status: 'PARTIAL',
      code: 'HOME_MESSAGE_GENERATION_REQUIRED',
    },
    {
      name: 'has an unset load generation',
      value: candidate(2, undefined, {
        generation: undefined as unknown as number,
        currentGeneration: undefined as unknown as number,
      }),
      status: 'PARTIAL',
      code: 'HOME_MESSAGE_GENERATION_REQUIRED',
    },
    {
      name: 'belongs to a stale conversation version',
      value: candidate(2, undefined, { currentConversationVersion: VERSION + 1 }),
      status: 'PARTIAL',
      code: 'HOME_MESSAGE_INVENTORY_STALE',
    },
    {
      name: 'belongs to a stale load generation',
      value: candidate(2, undefined, { currentGeneration: GENERATION + 1 }),
      status: 'PARTIAL',
      code: 'HOME_MESSAGE_INVENTORY_STALE',
    },
  ])('blocks $name', ({ value, status, code }) => {
    expect(assessMessageInventory(value)).toEqual({
      status,
      verified: false,
      errorCode: code,
    });
  });

  it('ignores stale reducer completion and never upgrades on selection', () => {
    const started = messageInventoryReducer({}, {
      type: 'LOAD_STARTED',
      id: 'conversation-1',
      conversationVersion: VERSION,
      expectedCount: 2,
      messages: [],
      generation: GENERATION,
    });
    const validCandidate = candidate(2, undefined, {
      generation: GENERATION - 1,
      currentGeneration: GENERATION - 1,
    });
    const stale = messageInventoryReducer(started, {
      type: 'LOAD_ASSESSED',
      id: 'conversation-1',
      generation: GENERATION - 1,
      candidate: validCandidate,
    });
    expect(stale).toBe(started);
    expect(stale['conversation-1']?.status).toBe('LOADING');

    // Conversation selection has no reducer action. Reusing the same state is
    // therefore incapable of changing inventory status.
    const selectedAgain: MessageInventoryMap = stale;
    expect(selectedAgain).toBe(stale);
  });

  it('recomputes assessment and rejects an incomplete candidate', () => {
    const started = messageInventoryReducer({}, {
      type: 'LOAD_STARTED',
      id: 'conversation-1',
      conversationVersion: VERSION,
      expectedCount: 2,
      messages: [],
      generation: GENERATION,
    });
    const result = messageInventoryReducer(started, {
      type: 'LOAD_ASSESSED',
      id: 'conversation-1',
      generation: GENERATION,
      candidate: candidate(2, undefined, { nextSequence: 1 }),
    });
    expect(result['conversation-1']?.status).toBe('PARTIAL');
    expect(result['conversation-1']?.verified).toBe(false);
  });

  it('allows mutation only for a current verified record', () => {
    const c = candidate(2);
    const started = messageInventoryReducer({}, {
      type: 'LOAD_STARTED',
      id: c.conversationId,
      conversationVersion: c.conversationVersion,
      expectedCount: c.expectedCount,
      messages: [],
      generation: c.generation,
    });
    const completed = messageInventoryReducer(started, {
      type: 'LOAD_ASSESSED',
      id: c.conversationId,
      generation: c.generation,
      candidate: c,
    });
    const record = completed[c.conversationId];
    expect(canMutateConversation(record, {
      conversationId: c.conversationId,
      conversationVersion: c.conversationVersion,
      expectedCount: c.expectedCount,
    })).toBe(true);
    expect(canMutateConversation(record, {
      conversationId: c.conversationId,
      conversationVersion: (c.conversationVersion ?? 0) + 1,
      expectedCount: c.expectedCount,
    })).toBe(false);
    expect(canMutateConversation({
      ...record!,
      conversationVersion: null,
    }, {
      conversationId: c.conversationId,
      conversationVersion: null,
      expectedCount: c.expectedCount,
    })).toBe(false);
    expect(canMutateConversation({
      ...record!,
      generation: 0,
    })).toBe(false);
  });

  it('holds the complete iff oracle across deterministic generated inventories', () => {
    let seed = 0x6d2b79f5;
    const next = (): number => {
      seed = Math.imul(seed ^ (seed >>> 15), seed | 1);
      seed ^= seed + Math.imul(seed ^ (seed >>> 7), seed | 61);
      return ((seed ^ (seed >>> 14)) >>> 0);
    };

    for (let sample = 0; sample < 128; sample += 1) {
      const count = next() % 10_001;
      const valid = candidate(count);
      expect(assessMessageInventory(valid).status).toBe('COMPLETE');

      if (count > 0) {
        const gap = [...valid.messages];
        gap[Math.floor(count / 2)] = message(count + 1);
        expect(assessMessageInventory(candidate(count, gap)).status)
          .not.toBe('COMPLETE');
      }
      expect(assessMessageInventory(candidate(count, valid.messages, {
        nextSequence: count || 1,
      })).status).not.toBe('COMPLETE');
      expect(assessMessageInventory(candidate(count, valid.messages, {
        partialErrors: [{ sequence: count, code: 'GENERATED_PARTIAL' }],
      })).status).not.toBe('COMPLETE');
      expect(assessMessageInventory(candidate(count, valid.messages, {
        locked: true,
      })).status).not.toBe('COMPLETE');
      expect(assessMessageInventory(candidate(count, valid.messages, {
        conversationVersion: null,
        currentConversationVersion: null,
      })).status).not.toBe('COMPLETE');
      expect(assessMessageInventory(candidate(count, valid.messages, {
        generation: 0,
        currentGeneration: 0,
      })).status).not.toBe('COMPLETE');
    }
  });
});
