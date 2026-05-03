import type { Conversation } from '../types';

const STORAGE_KEY = 'butler.conversations';

export function loadConversations(): Conversation[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as Conversation[]) : [];
  } catch {
    return [];
  }
}

export function saveConversations(convs: Conversation[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(convs));
  } catch {
    // localStorage quota exceeded — silently ignore
  }
}

export function upsertConversation(conv: Conversation): void {
  const convs = loadConversations();
  const idx = convs.findIndex(c => c.id === conv.id);
  if (idx >= 0) {
    convs[idx] = conv;
  } else {
    convs.unshift(conv);
  }
  saveConversations(convs);
}

export function deleteConversation(id: string): void {
  const convs = loadConversations().filter(c => c.id !== id);
  saveConversations(convs);
}

export function generateId(): string {
  return crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}
