import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../sidecarFetch', () => ({
  sidecarFetch: vi.fn(),
}));

import { sidecarFetch } from '../sidecarFetch';
import { fetchConversationMessages } from './client';
import type { Message } from '../../types';

const mockedFetch = vi.mocked(sidecarFetch);

function message(sequence: number): Message {
  return {
    id: `message-${sequence}`,
    role: sequence % 2 ? 'user' : 'butler',
    content: `content-${sequence}`,
    timestamp: '2026-07-23T00:00:00Z',
    sequence,
  };
}

function ok(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
}

function installContiguousProducer(total: number): void {
  mockedFetch.mockImplementation(async path => {
    const url = new URL(String(path), 'http://127.0.0.1');
    const after = Number(url.searchParams.get('after_sequence') ?? '0');
    const limit = Number(url.searchParams.get('limit') ?? '100');
    const items = Array.from(
      { length: Math.max(0, Math.min(limit, total - after)) },
      (_, index) => message(after + index + 1),
    );
    const last = items.at(-1)?.sequence ?? after;
    return ok({
      schema_version: 'butler.home.messages.v2',
      conversation_id: 'conversation-1',
      messages: items,
      message_count: total,
      conversation_version: 7,
      next_sequence: last < total ? last : null,
      partial_errors: [],
      locked: false,
    });
  });
}

describe('conversation message inventory pagination', () => {
  beforeEach(() => {
    mockedFetch.mockReset();
  });

  it.each([100, 101, 250, 1000])(
    'restores %i messages only after a contiguous terminal inventory',
    async total => {
      installContiguousProducer(total);
      const result = await fetchConversationMessages('conversation-1', total, {
        conversationVersion: 7,
      });
      expect(result.status).toBe('READY');
      expect(result.loaded_count).toBe(total);
      expect(result.messages.at(0)?.sequence).toBe(1);
      expect(result.messages.at(-1)?.sequence).toBe(total);
      expect(result.error_code).toBeNull();
    },
  );

  it('does not report COMPLETE for the audited [2,3] gap attack', async () => {
    mockedFetch.mockResolvedValue(ok({
      schema_version: 'butler.home.messages.v2',
      conversation_id: 'conversation-1',
      messages: [message(2), message(3)],
      message_count: 2,
      conversation_version: 7,
      next_sequence: null,
      partial_errors: [],
      locked: false,
    }));
    const result = await fetchConversationMessages('conversation-1', 2, {
      conversationVersion: 7,
    });
    expect(result.status).toBe('PARTIAL');
    expect(result.error_code).toBe('HOME_MESSAGE_SEQUENCE_GAP');
  });

  it('requires message_count instead of trusting a terminal cursor', async () => {
    mockedFetch.mockResolvedValue(ok({
      schema_version: 'butler.home.messages.v2',
      conversation_id: 'conversation-1',
      messages: [message(1)],
      conversation_version: 7,
      next_sequence: null,
      partial_errors: [],
      locked: false,
    }));
    const result = await fetchConversationMessages('conversation-1', 1, {
      conversationVersion: 7,
    });
    expect(result.status).toBe('ERROR');
    expect(result.error_code).toBe('HOME_MESSAGE_RESPONSE_SCHEMA_INVALID');
  });

  it('blocks a cursor that advances beyond the last returned sequence', async () => {
    mockedFetch.mockResolvedValue(ok({
      schema_version: 'butler.home.messages.v2',
      conversation_id: 'conversation-1',
      messages: [message(1)],
      message_count: 2,
      conversation_version: 7,
      next_sequence: 2,
      partial_errors: [],
      locked: false,
    }));
    const result = await fetchConversationMessages('conversation-1', 2, {
      conversationVersion: 7,
    });
    expect(result.status).toBe('PARTIAL');
    expect(result.error_code).toBe('HOME_MESSAGE_CURSOR_INVALID');
  });

  it('preserves a verified prefix and resumes from its last sequence', async () => {
    installContiguousProducer(250);
    const prefix = Array.from({ length: 100 }, (_, index) => message(index + 1));
    const result = await fetchConversationMessages('conversation-1', 250, {
      initialItems: prefix,
      conversationVersion: 7,
    });
    expect(result.status).toBe('READY');
    expect(result.loaded_count).toBe(250);
    expect(String(mockedFetch.mock.calls[0][0])).toContain('after_sequence=100');
  });

  it('preserves loaded messages when a later page fails', async () => {
    let calls = 0;
    mockedFetch.mockImplementation(async () => {
      calls += 1;
      if (calls === 2) throw new TypeError('network unavailable');
      return ok({
      schema_version: 'butler.home.messages.v2',
      conversation_id: 'conversation-1',
        messages: Array.from({ length: 100 }, (_, index) => message(index + 1)),
        message_count: 101,
        conversation_version: 7,
        next_sequence: 100,
        partial_errors: [],
        locked: false,
      });
    });
    const result = await fetchConversationMessages('conversation-1', 101, {
      conversationVersion: 7,
    });
    expect(result.status).toBe('PARTIAL');
    expect(result.loaded_count).toBe(100);
    expect(result.error_code).toBe('HOME_MESSAGE_PAGE_FAILED');
  });
});
