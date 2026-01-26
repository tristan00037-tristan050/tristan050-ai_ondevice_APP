import { IRegistryStore } from "./IRegistryStore";
import { PersistMap } from "../services/persist_maps";
import { persistReadJson, persistWriteJson } from "../services/persist_store";

export class FileStore implements IRegistryStore {
  kind: "file" = "file";

  private models = new PersistMap<any>("models.json");
  private modelVersions = new PersistMap<any>("model_versions.json");
  private artifacts = new PersistMap<any>("artifacts.json");
  private releasePointers = new PersistMap<any>("release_pointers.json");
  private updateStatesFile = "update_states.json";

  getModel(id: string) { return this.models.get(id) ?? null; }
  putModel(id: string, model: any) { this.models.set(id, model); }
  listModels() { return this.models.values(); }

  getModelVersion(id: string) { return this.modelVersions.get(id) ?? null; }
  putModelVersion(id: string, mv: any) { this.modelVersions.set(id, mv); }
  listModelVersions() { return this.modelVersions.values(); }

  getArtifact(id: string) { return this.artifacts.get(id) ?? null; }
  putArtifact(id: string, a: any) { this.artifacts.set(id, a); }
  listArtifacts() { return this.artifacts.values(); }

  getReleasePointer(id: string) { return this.releasePointers.get(id) ?? null; }
  putReleasePointer(id: string, rp: any) { this.releasePointers.set(id, rp); }
  listReleasePointers() { return this.releasePointers.values(); }

  clearAll() {
    // PersistMap에 deleteAll/clear가 없다면, ids를 순회해서 delete
    for (const [k] of this.models.entries()) this.models.delete(k);
    for (const [k] of this.modelVersions.entries()) this.modelVersions.delete(k);
    for (const [k] of this.artifacts.entries()) this.artifacts.delete(k);
    for (const [k] of this.releasePointers.entries()) this.releasePointers.delete(k);
    // UPDATE-02: clear update states
    persistWriteJson(this.updateStatesFile, {});
    this.flushNow();
  }

  flushNow() {
    this.models.flushNow();
    this.modelVersions.flushNow();
    this.artifacts.flushNow();
    this.releasePointers.flushNow();
  }

  // UPDATE-02: persisted anti-rollback state
  getUpdateState(key: string): any | null {
    const states = persistReadJson<Record<string, any>>(this.updateStatesFile) ?? {};
    return states[key] ?? null;
  }

  putUpdateState(key: string, state: any): void {
    const states = persistReadJson<Record<string, any>>(this.updateStatesFile) ?? {};
    states[key] = state;
    persistWriteJson(this.updateStatesFile, states);
  }

  // atomic monotonic bump (fail-closed on rollback)
  enforceAndBumpMaxSeenVersion(key: string, incomingVersion: number): number {
    // Use file lock via persistReadJson/persistWriteJson for atomicity
    const states = persistReadJson<Record<string, { max_seen_version: number }>>(this.updateStatesFile) ?? {};
    const current = states[key]?.max_seen_version ?? 0;

    // Fail-closed: rollback detection
    if (incomingVersion < current) {
      throw new Error(`ANTI_ROLLBACK: rollback_detected (incoming=${incomingVersion}, max_seen=${current})`);
    }

    // Idempotent: same version doesn't need update
    if (incomingVersion === current) {
      return current;
    }

    // Atomic update: incomingVersion > current
    states[key] = { max_seen_version: incomingVersion };
    persistWriteJson(this.updateStatesFile, states);
    return incomingVersion;
  }
}

