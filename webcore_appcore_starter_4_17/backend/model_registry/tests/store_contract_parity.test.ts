import { FileStore } from "../store/FileStore";
import { InMemoryDBStore } from "../store/InMemoryDBStore";
import type { IRegistryStore } from "../store/IRegistryStore";

function makeStores(): Array<[string, () => IRegistryStore]> {
  return [
    ["file", () => new FileStore()],
    ["memorydb", () => new InMemoryDBStore()],
  ];
}

describe.each(makeStores())("[EVID:STORE_CONTRACT_TESTS_SHARED_OK] store contract parity: %s", (_name, make) => {
  test("model basic put/get/list/delete", () => {
    const s = make();
    s.clearAll();

    s.putModel("m1", { id: "m1", name: "model-1" });
    expect(s.getModel("m1")).toMatchObject({ id: "m1" });

    const list = s.listModels();
    expect(Array.isArray(list)).toBe(true);
    expect(list.some((x: any) => x.id === "m1")).toBe(true);

    // Note: IRegistryStore doesn't have deleteModel, so we test clearAll instead
    s.clearAll();
    expect(s.getModel("m1")).toBeNull();
  });

  test("[EVID:DBSTORE_PARITY_SMOKE_OK] release pointer basic put/get", () => {
    const s = make();
    s.clearAll();

    s.putReleasePointer("rp1", { id: "rp1", model_id: "m1", version: "v1" });
    expect(s.getReleasePointer("rp1")).toMatchObject({ id: "rp1" });

    s.clearAll();
    expect(s.getReleasePointer("rp1")).toBeNull();
  });
});

