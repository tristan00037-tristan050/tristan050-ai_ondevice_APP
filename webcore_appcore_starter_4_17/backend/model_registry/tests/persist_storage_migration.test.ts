import { describe, it, expect, beforeEach } from "@jest/globals";
import { PersistMap } from "../services/persist_maps";
import fs from "node:fs";
import path from "node:path";

describe("P1-2: storage migrated to persistence (restart-safe)", () => {
  const dataDir = path.resolve(__dirname, "../data");
  const testFile = "models.json";
  const testFilePath = path.join(dataDir, testFile);

  beforeEach(() => {
    // Clean up test file before each test
    if (fs.existsSync(testFilePath)) {
      fs.unlinkSync(testFilePath);
    }
  });

  it("[EVID:PERSIST_STORAGE_RESTART_OK] data survives reload", () => {
    const key = "k_test_model";

    const m1 = new PersistMap<any>(testFile);
    m1.set(key, { id: key, v: 1 });
    // Force flush to ensure data is written before creating new instance
    m1.flushNow();

    // simulate restart by creating a new instance
    const m2 = new PersistMap<any>(testFile);
    const got = m2.get(key);

    expect(got).toBeTruthy();
    expect(got.id).toBe(key);
    expect(got.v).toBe(1);
  });

  it("PersistMap supports find and filter operations", () => {
    const m = new PersistMap<any>(testFile);
    m.set("k1", { id: "k1", tenant_id: "t1", name: "model1" });
    m.set("k2", { id: "k2", tenant_id: "t1", name: "model2" });
    m.set("k3", { id: "k3", tenant_id: "t2", name: "model3" });

    const found = m.find(m => m.tenant_id === "t1" && m.name === "model1");
    expect(found).toBeTruthy();
    expect(found?.id).toBe("k1");

    const filtered = m.filter(m => m.tenant_id === "t1");
    expect(filtered.length).toBe(2);
    expect(filtered.map(m => m.id)).toContain("k1");
    expect(filtered.map(m => m.id)).toContain("k2");
  });
});

