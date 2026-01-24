import { IRegistryStore } from "./IRegistryStore";
import { PersistMap } from "../services/persist_maps";

export class FileStore implements IRegistryStore {
  kind: "file" = "file";

  private models = new PersistMap<any>("models.json");
  private modelVersions = new PersistMap<any>("model_versions.json");
  private artifacts = new PersistMap<any>("artifacts.json");
  private releasePointers = new PersistMap<any>("release_pointers.json");

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
    this.flushNow();
  }

  flushNow() {
    this.models.flushNow();
    this.modelVersions.flushNow();
    this.artifacts.flushNow();
    this.releasePointers.flushNow();
  }
}

