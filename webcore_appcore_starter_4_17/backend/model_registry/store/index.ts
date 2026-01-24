import { IRegistryStore } from "./IRegistryStore";
import { FileStore } from "./FileStore";

let singleton: IRegistryStore | null = null;

export function getRegistryStore(): IRegistryStore {
  if (singleton) return singleton;
  singleton = new FileStore();
  return singleton;
}

