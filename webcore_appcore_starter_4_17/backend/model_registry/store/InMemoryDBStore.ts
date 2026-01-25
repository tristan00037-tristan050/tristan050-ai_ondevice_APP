import type { IRegistryStore } from "./IRegistryStore";

/**
 * STORE-01 skeleton: DBStore parity harness.
 * - Not a real DB adapter yet.
 * - Used to guarantee interface-level parity via shared contract tests.
 */
export class InMemoryDBStore implements IRegistryStore {
  kind: "file" = "file"; // Temporary: match FileStore kind for interface compatibility

  // Minimal in-memory structures; shape is intentionally generic.
  private models = new Map<string, any>();
  private modelVersions = new Map<string, any>();
  private artifacts = new Map<string, any>();
  private releasePointers = new Map<string, any>();

  // Models
  getModel(id: string): any | null {
    return this.models.get(id) ?? null;
  }

  putModel(id: string, model: any): void {
    this.models.set(id, model);
  }

  listModels(): any[] {
    return Array.from(this.models.values());
  }

  // ModelVersions
  getModelVersion(id: string): any | null {
    return this.modelVersions.get(id) ?? null;
  }

  putModelVersion(id: string, mv: any): void {
    this.modelVersions.set(id, mv);
  }

  listModelVersions(): any[] {
    return Array.from(this.modelVersions.values());
  }

  // Artifacts
  getArtifact(id: string): any | null {
    return this.artifacts.get(id) ?? null;
  }

  putArtifact(id: string, a: any): void {
    this.artifacts.set(id, a);
  }

  listArtifacts(): any[] {
    return Array.from(this.artifacts.values());
  }

  // Release pointers
  getReleasePointer(id: string): any | null {
    return this.releasePointers.get(id) ?? null;
  }

  putReleasePointer(id: string, rp: any): void {
    this.releasePointers.set(id, rp);
  }

  listReleasePointers(): any[] {
    return Array.from(this.releasePointers.values());
  }

  // Maintenance
  clearAll(): void {
    this.models.clear();
    this.modelVersions.clear();
    this.artifacts.clear();
    this.releasePointers.clear();
  }

  flushNow(): void {
    // In-memory store doesn't need flush
  }
}

