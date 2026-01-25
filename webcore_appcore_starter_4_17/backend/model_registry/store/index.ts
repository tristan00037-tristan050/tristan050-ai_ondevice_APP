import { IRegistryStore } from "./IRegistryStore";
import { FileStore } from "./FileStore";
import { InMemoryDBStore } from "./InMemoryDBStore";

let singleton: IRegistryStore | null = null;

export function getRegistryStore(): IRegistryStore {
  if (singleton) return singleton;
  // STORE-01: parity harness (default: FileStore)
  // Use REGISTRY_STORE_BACKEND=memorydb for contract parity tests only.
  const backend = process.env.REGISTRY_STORE_BACKEND || "file";
  if (backend === "memorydb") {
    singleton = new InMemoryDBStore();
  } else {
    singleton = new FileStore();
  }
  return singleton;
}

