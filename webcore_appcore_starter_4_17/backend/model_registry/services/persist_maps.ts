import { persistReadJson, persistWriteJson } from "./persist_store";

export class PersistMap<V> {
  private loaded = false;
  private map = new Map<string, V>();
  constructor(private file: string) {}

  private ensureLoaded() {
    if (this.loaded) return;
    const data = persistReadJson<Record<string, V>>(this.file) ?? {};
    this.map = new Map(Object.entries(data));
    this.loaded = true;
  }

  private flush() {
    const obj: Record<string, V> = {};
    for (const [k, v] of this.map.entries()) obj[k] = v;
    persistWriteJson(this.file, obj);
  }

  get(key: string): V | undefined {
    this.ensureLoaded();
    return this.map.get(key);
  }

  set(key: string, val: V) {
    this.ensureLoaded();
    this.map.set(key, val);
    this.flush();
  }

  has(key: string): boolean {
    this.ensureLoaded();
    return this.map.has(key);
  }

  delete(key: string): boolean {
    this.ensureLoaded();
    const ok = this.map.delete(key);
    this.flush();
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
    this.flush();
  }

  get length(): number {
    this.ensureLoaded();
    return this.map.size;
  }
}

