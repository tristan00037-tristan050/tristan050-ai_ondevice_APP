import { persistReadJson, persistWriteJson } from "./persist_store";
import { registerPersist, hookProcessFlush } from "./persist_registry";

export class PersistMap<V> {
  private loaded = false;
  private map = new Map<string, V>();
  private dirty = false;
  private flushTimer: NodeJS.Timeout | null = null;
  private flushDelayMs = 200;

  constructor(private file: string) {
    registerPersist(this);
    hookProcessFlush();
  }

  private ensureLoaded() {
    if (this.loaded) return;
    const data = persistReadJson<Record<string, V>>(this.file) ?? {};
    this.map = new Map(Object.entries(data));
    this.loaded = true;
  }

  private flush() {
    const obj: Record<string, V> = {};
    for (const [k, v] of this.map.entries()) obj[k] = v;
    // Always write, even if empty (to allow clearing)
    persistWriteJson(this.file, obj);
  }

  private scheduleFlush() {
    this.dirty = true;
    if (this.flushTimer) return;
    this.flushTimer = setTimeout(() => {
      this.flushTimer = null;
      this.flushNow();
    }, this.flushDelayMs);
  }

  flushNow() {
    this.ensureLoaded();
    if (!this.dirty) return;
    this.dirty = false;
    if (this.flushTimer) {
      clearTimeout(this.flushTimer);
      this.flushTimer = null;
    }
    // 기존 flush 로직 호출
    this.flush();
  }

  get(key: string): V | undefined {
    this.ensureLoaded();
    return this.map.get(key);
  }

  set(key: string, val: V) {
    this.ensureLoaded();
    this.map.set(key, val);
    this.scheduleFlush();
  }

  has(key: string): boolean {
    this.ensureLoaded();
    return this.map.has(key);
  }

  delete(key: string): boolean {
    this.ensureLoaded();
    const ok = this.map.delete(key);
    if (ok) {
      this.scheduleFlush();
    }
    return ok;
  }

  entries(): [string, V][] {
    this.ensureLoaded();
    return Array.from(this.map.entries());
  }

  values(): V[] {
    this.ensureLoaded();
    return Array.from(this.map.values());
  }

  find(predicate: (value: V) => boolean): V | undefined {
    this.ensureLoaded();
    return Array.from(this.map.values()).find(predicate);
  }

  filter(predicate: (value: V) => boolean): V[] {
    this.ensureLoaded();
    return Array.from(this.map.values()).filter(predicate);
  }

  push(val: V & { id: string }) {
    this.ensureLoaded();
    this.map.set(val.id, val);
    this.scheduleFlush();
  }

  get length(): number {
    this.ensureLoaded();
    return this.map.size;
  }
}

