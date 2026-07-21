import Foundation
import SQLite3

private let SQLITE_TRANSIENT = unsafeBitCast(-1, to: sqlite3_destructor_type.self)

final class A4ReplayLedger {
    private var database: OpaquePointer?
    private let lock = NSLock()

    init() throws {
        let manager = FileManager.default
        let base = try manager.url(
            for: .applicationSupportDirectory,
            in: .userDomainMask,
            appropriateFor: nil,
            create: true
        )
        let directory = base.appendingPathComponent("Butler/Security", isDirectory: true)
        try manager.createDirectory(
            at: directory,
            withIntermediateDirectories: true,
            attributes: [.posixPermissions: 0o700]
        )
        let path = directory.appendingPathComponent("a4-authority-replay-v53.sqlite").path
        guard sqlite3_open_v2(
            path,
            &database,
            SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE | SQLITE_OPEN_FULLMUTEX,
            nil
        ) == SQLITE_OK else {
            throw A4NativeError.storageAtomicity
        }
        sqlite3_busy_timeout(database, 2_000)
        try execute("PRAGMA journal_mode=WAL")
        try execute("PRAGMA synchronous=FULL")
        try execute("PRAGMA secure_delete=ON")
        try execute("""
            CREATE TABLE IF NOT EXISTS attestations(
                nonce_digest TEXT PRIMARY KEY NOT NULL,
                request_id TEXT UNIQUE NOT NULL,
                payload_digest TEXT NOT NULL,
                key_epoch INTEGER NOT NULL,
                terminal_outcome TEXT NOT NULL,
                signature_digest TEXT,
                created_unix_ms INTEGER NOT NULL
            ) STRICT
        """)
        _ = chmod(path, 0o600)
    }

    deinit {
        sqlite3_close(database)
    }

    private func execute(_ statement: String) throws {
        guard sqlite3_exec(database, statement, nil, nil, nil) == SQLITE_OK else {
            throw A4NativeError.storageAtomicity
        }
    }

    func reserve(
        nonceDigest: String,
        requestID: String,
        payloadDigest: String,
        keyEpoch: Int
    ) throws {
        lock.lock()
        defer { lock.unlock() }
        try execute("BEGIN IMMEDIATE")
        var statement: OpaquePointer?
        defer { sqlite3_finalize(statement) }
        let sql = """
            INSERT INTO attestations(
                nonce_digest,request_id,payload_digest,key_epoch,
                terminal_outcome,created_unix_ms
            ) VALUES(?,?,?,?,?,?)
        """
        guard sqlite3_prepare_v2(database, sql, -1, &statement, nil) == SQLITE_OK else {
            try? execute("ROLLBACK")
            throw A4NativeError.storageAtomicity
        }
        sqlite3_bind_text(statement, 1, nonceDigest, -1, SQLITE_TRANSIENT)
        sqlite3_bind_text(statement, 2, requestID, -1, SQLITE_TRANSIENT)
        sqlite3_bind_text(statement, 3, payloadDigest, -1, SQLITE_TRANSIENT)
        sqlite3_bind_int64(statement, 4, sqlite3_int64(keyEpoch))
        sqlite3_bind_text(statement, 5, "PENDING", -1, SQLITE_TRANSIENT)
        sqlite3_bind_int64(statement, 6, sqlite3_int64(Date().timeIntervalSince1970 * 1_000))
        guard sqlite3_step(statement) == SQLITE_DONE else {
            try? execute("ROLLBACK")
            throw A4NativeError.replay
        }
        try execute("COMMIT")
    }

    func commit(nonceDigest: String, signatureDigest: String) throws {
        lock.lock()
        defer { lock.unlock() }
        try execute("BEGIN IMMEDIATE")
        var statement: OpaquePointer?
        defer { sqlite3_finalize(statement) }
        let sql = """
            UPDATE attestations
               SET terminal_outcome='PASS',signature_digest=?
             WHERE nonce_digest=? AND terminal_outcome='PENDING'
        """
        guard sqlite3_prepare_v2(database, sql, -1, &statement, nil) == SQLITE_OK else {
            try? execute("ROLLBACK")
            throw A4NativeError.storageAtomicity
        }
        sqlite3_bind_text(statement, 1, signatureDigest, -1, SQLITE_TRANSIENT)
        sqlite3_bind_text(statement, 2, nonceDigest, -1, SQLITE_TRANSIENT)
        guard sqlite3_step(statement) == SQLITE_DONE, sqlite3_changes(database) == 1 else {
            try? execute("ROLLBACK")
            throw A4NativeError.storageAtomicity
        }
        try execute("COMMIT")
    }
}
