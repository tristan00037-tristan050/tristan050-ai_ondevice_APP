import { describe, it, expect, beforeEach } from "@jest/globals";
import fs from "node:fs";
import path from "node:path";
import { persistWriteJson, persistReadJson } from "../services/persist_store";

describe("P1-3 persistence: atomic write + corruption fail-closed", () => {
  const dataDir = path.resolve(__dirname, "../data");

  beforeEach(() => {
    // Clean up test files
    const testFiles = ["atomic_test.json", "corrupt_test.json"];
    testFiles.forEach(file => {
      const filePath = path.join(dataDir, file);
      const tmpPath = filePath + ".tmp";
      if (fs.existsSync(filePath)) fs.unlinkSync(filePath);
      if (fs.existsSync(tmpPath)) fs.unlinkSync(tmpPath);
    });
  });

  it("[EVID:PERSIST_ATOMIC_WRITE_OK] write creates final file without tmp leftover", () => {
    persistWriteJson("atomic_test.json", { a: 1 });
    const finalPath = path.join(dataDir, "atomic_test.json");
    const tmpPath = finalPath + ".tmp";

    expect(fs.existsSync(finalPath)).toBe(true);
    expect(fs.existsSync(tmpPath)).toBe(false);

    // Verify content is correct
    const content = persistReadJson<{ a: number }>("atomic_test.json");
    expect(content).toBeTruthy();
    expect(content?.a).toBe(1);
  });

  it("[EVID:PERSIST_CORRUPTION_FAILCLOSED_OK] corrupted json throws", () => {
    const finalPath = path.join(dataDir, "corrupt_test.json");
    fs.mkdirSync(dataDir, { recursive: true });
    fs.writeFileSync(finalPath, "{not-json", "utf8");

    expect(() => persistReadJson<any>("corrupt_test.json")).toThrow(/PERSIST_CORRUPTED/);
  });
});

