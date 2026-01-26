export type StoreKind = "file";

export interface IRegistryStore {
  kind: StoreKind;

  // Models
  getModel(id: string): any | null;
  putModel(id: string, model: any): void;
  listModels(): any[];

  // ModelVersions
  getModelVersion(id: string): any | null;
  putModelVersion(id: string, mv: any): void;
  listModelVersions(): any[];

  // Artifacts
  getArtifact(id: string): any | null;
  putArtifact(id: string, a: any): void;
  listArtifacts(): any[];

  // Release pointers
  getReleasePointer(id: string): any | null;
  putReleasePointer(id: string, rp: any): void;
  listReleasePointers(): any[];

  // Maintenance
  clearAll(): void;
  flushNow(): void; // batch flush 환경에서 강제 flush

  // UPDATE-02: persisted anti-rollback state
  getUpdateState(key: string): any | null;
  putUpdateState(key: string, state: any): void;

  // atomic monotonic bump (fail-closed on rollback)
  enforceAndBumpMaxSeenVersion(key: string, incomingVersion: number): number;
}

