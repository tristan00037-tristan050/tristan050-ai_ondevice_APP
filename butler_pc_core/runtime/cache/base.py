"""
cache/base.py
=============
4종 캐시 공통 인터페이스 + SQLite 백엔드 (WAL 모드, LRU eviction).

각 캐시 인스턴스는 독립적인 SQLite 테이블을 사용하며
최대 256 MB / 총 1 GB 한도를 LRU로 관리한다.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional

_DEFAULT_DB = Path(__file__).resolve().parent.parent.parent / "data" / "cache.db"

# 테이블당 크기 한도 (bytes)
TABLE_SIZE_LIMIT = 256 * 1024 * 1024  # 256 MB


def _open_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-8192")  # 8 MB page cache
    return conn


class BaseCache(ABC):
    """캐시 공통 인터페이스."""

    def __init__(
        self,
        table: str,
        db_path: Path = _DEFAULT_DB,
        ttl_seconds: Optional[int] = None,
        size_limit: int = TABLE_SIZE_LIMIT,
    ):
        self._table = table
        self._ttl = ttl_seconds
        self._size_limit = size_limit
        self._lock = threading.Lock()
        self._conn = _open_db(db_path)
        self._hit = 0
        self._miss = 0
        self._init_table()

    # ------------------------------------------------------------------
    # 퍼블릭 API
    # ------------------------------------------------------------------

    def get(self, key: str) -> Optional[Any]:
        now = time.time()
        with self._lock:
            row = self._conn.execute(
                f"SELECT value, expires_at FROM {self._table} WHERE key=?", (key,)
            ).fetchone()
            if row is None:
                self._miss += 1
                return None
            value_str, expires_at = row
            if expires_at is not None and expires_at < now:
                self._conn.execute(
                    f"DELETE FROM {self._table} WHERE key=?", (key,)
                )
                self._conn.commit()
                self._miss += 1
                return None
            # LRU: accessed_at 갱신
            self._conn.execute(
                f"UPDATE {self._table} SET accessed_at=? WHERE key=?", (now, key)
            )
            self._conn.commit()
            self._hit += 1
            return json.loads(value_str)

    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        ttl = ttl_seconds if ttl_seconds is not None else self._ttl
        expires_at = time.time() + ttl if ttl else None
        value_str = json.dumps(value, ensure_ascii=False, default=str)
        size_bytes = len(value_str.encode())
        now = time.time()
        with self._lock:
            self._conn.execute(
                f"""INSERT INTO {self._table} (key, value, size_bytes, created_at, accessed_at, expires_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET
                        value=excluded.value,
                        size_bytes=excluded.size_bytes,
                        accessed_at=excluded.accessed_at,
                        expires_at=excluded.expires_at""",
                (key, value_str, size_bytes, now, now, expires_at),
            )
            self._conn.commit()
            self._evict_if_needed()

    def invalidate(self, pattern: str) -> int:
        sql_pattern = pattern.replace("*", "%")
        with self._lock:
            cur = self._conn.execute(
                f"DELETE FROM {self._table} WHERE key LIKE ?", (sql_pattern,)
            )
            self._conn.commit()
            return cur.rowcount

    def stats(self) -> dict:
        with self._lock:
            row = self._conn.execute(
                f"SELECT COUNT(*), COALESCE(SUM(size_bytes),0) FROM {self._table}"
            ).fetchone()
        count, total_bytes = row
        total = self._hit + self._miss
        return {
            "table": self._table,
            "entry_count": count,
            "size_bytes": total_bytes,
            "hit_count": self._hit,
            "miss_count": self._miss,
            "hit_rate": round(self._hit / total, 4) if total else 0.0,
        }

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ------------------------------------------------------------------
    # 키 빌더 (서브클래스 구현)
    # ------------------------------------------------------------------

    @abstractmethod
    def build_key(self, **kwargs: Any) -> str: ...

    # ------------------------------------------------------------------
    # 내부 유틸
    # ------------------------------------------------------------------

    def _init_table(self) -> None:
        with self._lock:
            self._conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {self._table} (
                    key         TEXT PRIMARY KEY,
                    value       TEXT NOT NULL,
                    size_bytes  INTEGER NOT NULL DEFAULT 0,
                    created_at  REAL NOT NULL,
                    accessed_at REAL NOT NULL,
                    expires_at  REAL
                )
            """)
            self._conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{self._table}_accessed"
                f" ON {self._table}(accessed_at)"
            )
            self._conn.commit()

    def _evict_if_needed(self) -> None:
        row = self._conn.execute(
            f"SELECT COALESCE(SUM(size_bytes),0) FROM {self._table}"
        ).fetchone()
        total = row[0]
        if total <= self._size_limit:
            return
        # LRU: accessed_at 오름차순으로 삭제
        while total > self._size_limit * 0.8:
            victim = self._conn.execute(
                f"SELECT key, size_bytes FROM {self._table} ORDER BY accessed_at ASC LIMIT 1"
            ).fetchone()
            if victim is None:
                break
            self._conn.execute(
                f"DELETE FROM {self._table} WHERE key=?", (victim[0],)
            )
            total -= victim[1]
        self._conn.commit()
