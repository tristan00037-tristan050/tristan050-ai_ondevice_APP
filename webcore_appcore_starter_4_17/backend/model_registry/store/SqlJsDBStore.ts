/**
 * STORE-02: Real DB adapter using sql.js (WASM-based SQLite)
 * - Implements IRegistryStore with SQLite backend
 * - Transaction-based atomic operations
 * - Binary file persistence (tmp→fsync→rename pattern)
 */

import type { IRegistryStore } from "./IRegistryStore";
import initSqlJs, { Database } from "sql.js";
import fs from "node:fs";
import path from "node:path";

const DATA_DIR = path.resolve(__dirname, "../data");

// Global SQL.js module (initialized once, shared across instances)
let SQL_MODULE: any = null;
let SQL_INIT_PROMISE: Promise<any> | null = null;

async function getSQLModule(): Promise<any> {
  if (SQL_MODULE) return SQL_MODULE;
  if (!SQL_INIT_PROMISE) {
    SQL_INIT_PROMISE = initSqlJs().then((SQL) => {
      SQL_MODULE = SQL;
      return SQL;
    });
  }
  return SQL_INIT_PROMISE;
}

interface SqlJsDBStoreConfig {
  dbPath: string;
}

export class SqlJsDBStore implements IRegistryStore {
  kind: "file" = "file";
  private db: Database | null = null;
  private dbPath: string;
  private initPromise: Promise<void> | null = null;

  constructor(config?: SqlJsDBStoreConfig) {
    this.dbPath = config?.dbPath || path.join(DATA_DIR, "registry.db");
    this.ensureDir();
  }

  private ensureDir() {
    fs.mkdirSync(DATA_DIR, { recursive: true });
  }

  async init(): Promise<void> {
    if (this.db) return;
    if (this.initPromise) return this.initPromise;

    this.initPromise = (async () => {
      const SQL = await getSQLModule();
      
      // Load existing DB or create new
      if (fs.existsSync(this.dbPath)) {
        const buffer = fs.readFileSync(this.dbPath);
        this.db = new SQL.Database(buffer);
      } else {
        this.db = new SQL.Database();
        this.createTables();
        this.flushNow(); // Save initial empty DB
      }
    })();

    return this.initPromise;
  }

  private ensureDB() {
    if (!this.db) {
      throw new Error("DB not initialized. Call init() first.");
    }
    return this.db;
  }

  private createTables() {
    const db = this.ensureDB();
    db.run(`
      CREATE TABLE IF NOT EXISTS models (
        id TEXT PRIMARY KEY,
        data TEXT NOT NULL
      )
    `);
    db.run(`
      CREATE TABLE IF NOT EXISTS model_versions (
        id TEXT PRIMARY KEY,
        data TEXT NOT NULL
      )
    `);
    db.run(`
      CREATE TABLE IF NOT EXISTS artifacts (
        id TEXT PRIMARY KEY,
        data TEXT NOT NULL
      )
    `);
    db.run(`
      CREATE TABLE IF NOT EXISTS release_pointers (
        id TEXT PRIMARY KEY,
        data TEXT NOT NULL
      )
    `);
    db.run(`
      CREATE TABLE IF NOT EXISTS update_states (
        key TEXT PRIMARY KEY,
        data TEXT NOT NULL
      )
    `);
  }

  // Models
  getModel(id: string): any | null {
    const db = this.ensureDB();
    const stmt = db.prepare("SELECT data FROM models WHERE id = ?");
    stmt.bind([id]);
    const row = stmt.step() ? stmt.getAsObject() : null;
    stmt.free();
    return row ? JSON.parse(row.data as string) : null;
  }

  putModel(id: string, model: any): void {
    const db = this.ensureDB();
    const data = JSON.stringify(model);
    db.run("INSERT OR REPLACE INTO models (id, data) VALUES (?, ?)", [id, data]);
  }

  listModels(): any[] {
    const db = this.ensureDB();
    const stmt = db.prepare("SELECT data FROM models");
    const results: any[] = [];
    while (stmt.step()) {
      const row = stmt.getAsObject();
      results.push(JSON.parse(row.data as string));
    }
    stmt.free();
    return results;
  }

  // ModelVersions
  getModelVersion(id: string): any | null {
    const db = this.ensureDB();
    const stmt = db.prepare("SELECT data FROM model_versions WHERE id = ?");
    stmt.bind([id]);
    const row = stmt.step() ? stmt.getAsObject() : null;
    stmt.free();
    return row ? JSON.parse(row.data as string) : null;
  }

  putModelVersion(id: string, mv: any): void {
    const db = this.ensureDB();
    const data = JSON.stringify(mv);
    db.run("INSERT OR REPLACE INTO model_versions (id, data) VALUES (?, ?)", [id, data]);
  }

  listModelVersions(): any[] {
    const db = this.ensureDB();
    const stmt = db.prepare("SELECT data FROM model_versions");
    const results: any[] = [];
    while (stmt.step()) {
      const row = stmt.getAsObject();
      results.push(JSON.parse(row.data as string));
    }
    stmt.free();
    return results;
  }

  // Artifacts
  getArtifact(id: string): any | null {
    const db = this.ensureDB();
    const stmt = db.prepare("SELECT data FROM artifacts WHERE id = ?");
    stmt.bind([id]);
    const row = stmt.step() ? stmt.getAsObject() : null;
    stmt.free();
    return row ? JSON.parse(row.data as string) : null;
  }

  putArtifact(id: string, a: any): void {
    const db = this.ensureDB();
    const data = JSON.stringify(a);
    db.run("INSERT OR REPLACE INTO artifacts (id, data) VALUES (?, ?)", [id, data]);
  }

  listArtifacts(): any[] {
    const db = this.ensureDB();
    const stmt = db.prepare("SELECT data FROM artifacts");
    const results: any[] = [];
    while (stmt.step()) {
      const row = stmt.getAsObject();
      results.push(JSON.parse(row.data as string));
    }
    stmt.free();
    return results;
  }

  // Release pointers
  getReleasePointer(id: string): any | null {
    const db = this.ensureDB();
    const stmt = db.prepare("SELECT data FROM release_pointers WHERE id = ?");
    stmt.bind([id]);
    const row = stmt.step() ? stmt.getAsObject() : null;
    stmt.free();
    return row ? JSON.parse(row.data as string) : null;
  }

  putReleasePointer(id: string, rp: any): void {
    const db = this.ensureDB();
    const data = JSON.stringify(rp);
    db.run("INSERT OR REPLACE INTO release_pointers (id, data) VALUES (?, ?)", [id, data]);
  }

  listReleasePointers(): any[] {
    const db = this.ensureDB();
    const stmt = db.prepare("SELECT data FROM release_pointers");
    const results: any[] = [];
    while (stmt.step()) {
      const row = stmt.getAsObject();
      results.push(JSON.parse(row.data as string));
    }
    stmt.free();
    return results;
  }

  // Maintenance
  clearAll(): void {
    const db = this.ensureDB();
    db.run("DELETE FROM models");
    db.run("DELETE FROM model_versions");
    db.run("DELETE FROM artifacts");
    db.run("DELETE FROM release_pointers");
    db.run("DELETE FROM update_states");
    this.flushNow();
  }

  flushNow(): void {
    if (!this.db) return;
    const db = this.ensureDB();
    const buffer = db.export();
    
    // Atomic write: tmp→fsync→rename (same pattern as persistWriteJson)
    const tmp = this.dbPath + ".tmp";
    fs.writeFileSync(tmp, buffer);
    
    // fsync
    const fd = fs.openSync(tmp, "r+");
    try {
      fs.fsyncSync(fd);
    } finally {
      fs.closeSync(fd);
    }
    
    // Atomic rename
    fs.renameSync(tmp, this.dbPath);
  }

  // UPDATE-02: persisted anti-rollback state
  getUpdateState(key: string): any | null {
    const db = this.ensureDB();
    const stmt = db.prepare("SELECT data FROM update_states WHERE key = ?");
    stmt.bind([key]);
    const row = stmt.step() ? stmt.getAsObject() : null;
    stmt.free();
    return row ? JSON.parse(row.data as string) : null;
  }

  putUpdateState(key: string, state: any): void {
    const db = this.ensureDB();
    const data = JSON.stringify(state);
    db.run("INSERT OR REPLACE INTO update_states (key, data) VALUES (?, ?)", [key, data]);
  }

  // atomic monotonic bump (fail-closed on rollback)
  enforceAndBumpMaxSeenVersion(key: string, incomingVersion: number): number {
    const db = this.ensureDB();
    
    // Transaction: BEGIN
    db.run("BEGIN TRANSACTION");
    
    try {
      // Get current max_seen_version
      const stmt = db.prepare("SELECT data FROM update_states WHERE key = ?");
      stmt.bind([key]);
      const row = stmt.step() ? stmt.getAsObject() : null;
      stmt.free();
      
      const current = row ? JSON.parse(row.data as string).max_seen_version ?? 0 : 0;
      
      // Fail-closed: rollback detection
      if (incomingVersion < current) {
        db.run("ROLLBACK");
        throw new Error(`ANTI_ROLLBACK: rollback_detected (incoming=${incomingVersion}, max_seen=${current})`);
      }
      
      // Idempotent: same version doesn't need update
      if (incomingVersion === current) {
        db.run("COMMIT");
        return current;
      }
      
      // Atomic update: incomingVersion > current
      const newState = { max_seen_version: incomingVersion };
      const data = JSON.stringify(newState);
      db.run("INSERT OR REPLACE INTO update_states (key, data) VALUES (?, ?)", [key, data]);
      
      // Transaction: COMMIT
      db.run("COMMIT");
      return incomingVersion;
    } catch (err) {
      // Ensure rollback on any error
      try {
        db.run("ROLLBACK");
      } catch {
        // Ignore rollback errors
      }
      throw err;
    }
  }

  // Helper to reset SQL module (for tests)
  static resetSQLModule(): void {
    SQL_MODULE = null;
    SQL_INIT_PROMISE = null;
  }
}
