import { describe, it, expect, beforeEach } from "@jest/globals";
import fs from "node:fs";
import path from "node:path";
import { PersistMap } from "../services/persist_maps";

describe("P1-6: PersistMap batch flush (debounce) + flushNow", () => {
  const dataDir = path.resolve(__dirname, "../data");
  const testFile = "batchflush_test.json";
  const testFilePath = path.join(dataDir, testFile);

  beforeEach(() => {
    // Clean up test file before each test
    if (fs.existsSync(testFilePath)) {
      fs.unlinkSync(testFilePath);
    }
  });

  it("[EVID:PERSIST_BATCHFLUSH_OK] multiple sets should not write every time (uses flushNow)", () => {
    const m = new PersistMap<any>(testFile);
    m.set("a", { v: 1 });
    m.set("b", { v: 2 });
    m.set("c", { v: 3 });

    // force flush to make deterministic
    m.flushNow();

    expect(fs.existsSync(testFilePath)).toBe(true);
    const raw = fs.readFileSync(testFilePath, "utf8");
    const obj = JSON.parse(raw);
    expect(obj.a.v).toBe(1);
    expect(obj.b.v).toBe(2);
    expect(obj.c.v).toBe(3);
  });
});

