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
  void convs;
  // The canonical store is the sidecar SQLite database. localStorage is read
  // once only as a legacy migration source.
}

export function upsertConversation(conv: Conversation): void {
  void conv;
}

export function deleteConversation(id: string): void {
  void id;
}

export function clearLegacyConversations(): void {
  localStorage.removeItem(STORAGE_KEY);
}

export function generateId(): string {
  return crypto.randomUUID();
}
