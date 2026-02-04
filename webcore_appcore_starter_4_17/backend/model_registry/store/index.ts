import { IRegistryStore } from "./IRegistryStore";
import { FileStore } from "./FileStore";
import { InMemoryDBStore } from "./InMemoryDBStore";
import { SqlJsDBStore } from "./SqlJsDBStore";

let singleton: IRegistryStore | null = null;

export function getRegistryStore(): IRegistryStore {
  if (singleton) return singleton;
  // STORE-01: parity harness (default: FileStore)
  // STORE-02: real DB adapter (sqljs)
  // Use REGISTRY_STORE_BACKEND=memorydb for contract parity tests only.
  // Use REGISTRY_STORE_BACKEND=sqljs for real DB adapter tests.
  const backend = process.env.REGISTRY_STORE_BACKEND || "file";
  if (backend === "memorydb") {
    singleton = new InMemoryDBStore();
  } else if (backend === "sqljs") {
    singleton = new SqlJsDBStore();
  } else {
    singleton = new FileStore();
  }
  return singleton;
}

// Test-only: reset singleton for test isolation
export function resetRegistryStoreForTests(): void {
  singleton = null;
}

