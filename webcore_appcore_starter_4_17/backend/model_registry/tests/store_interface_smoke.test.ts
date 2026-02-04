import { describe, it, expect } from "@jest/globals";
import { getRegistryStore } from "../store";

describe("P1-3: IRegistryStore boundary smoke", () => {
  it("[EVID:STORE_INTERFACE_ABSTRACTED_OK] FileStore implements IRegistryStore and works", () => {
    const s = getRegistryStore();
    s.clearAll();

    s.putModel("m1", { id: "m1" });
    expect(s.getModel("m1")?.id).toBe("m1");

    s.flushNow();
    expect(s.listModels().length).toBeGreaterThan(0);
  });
});

