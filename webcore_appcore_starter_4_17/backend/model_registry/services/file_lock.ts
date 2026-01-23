import fs from "node:fs";
import path from "node:path";

const DATA_DIR = path.resolve(__dirname, "../data");

function lockPath(name: string) {
  return path.join(DATA_DIR, `${name}.lock`);
}

export function withFileLock<T>(name: string, fn: () => T): T {
  fs.mkdirSync(DATA_DIR, { recursive: true });
  const lp = lockPath(name);

  // Retry logic for lock acquisition (handles race conditions in test cleanup)
  const maxRetries = 10;
  const retryDelay = 10; // ms
  
  for (let attempt = 0; attempt < maxRetries; attempt++) {
    try {
      // simple lock: create lock file exclusively
      const fd = fs.openSync(lp, "wx"); // throws if exists
      try {
        return fn();
      } finally {
        fs.closeSync(fd);
        if (fs.existsSync(lp)) {
          fs.unlinkSync(lp);
        }
      }
    } catch (error: any) {
      if (error.code === 'EEXIST' && attempt < maxRetries - 1) {
        // Lock file exists, wait and retry
        const sleep = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));
        // Use synchronous sleep for simplicity (blocking)
        const start = Date.now();
        while (Date.now() - start < retryDelay) {
          // busy wait
        }
        continue;
      }
      throw error;
    }
  }
  
  throw new Error(`Failed to acquire lock after ${maxRetries} attempts`);
}

