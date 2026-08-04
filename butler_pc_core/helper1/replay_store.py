"""Persistent atomic replay protection for signed Helper1 evidence."""
from __future__ import annotations

import hashlib
import ipaddress
import os
import re
import socket
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol, runtime_checkable
from urllib.parse import parse_qsl, urlsplit

NONCE_RE = re.compile(r"^[A-Za-z0-9_-]{22,128}$")
KEY_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{7,127}$")
DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


class ReplayStoreError(RuntimeError):
    pass


def _nonce_digest(nonce: str) -> str:
    if type(nonce) is not str or NONCE_RE.fullmatch(nonce) is None:
        raise ReplayStoreError("EVIDENCE_NONCE_INVALID")
    return hashlib.sha256(nonce.encode("ascii")).hexdigest()


@dataclass(frozen=True, slots=True)
class ReplayReservation:
    policy_sha256: str
    key_id: str
    nonce: str
    expires_at_epoch_s: int

    def __post_init__(self) -> None:
        if type(self.policy_sha256) is not str or DIGEST_RE.fullmatch(self.policy_sha256) is None:
            raise ReplayStoreError("REPLAY_POLICY_DIGEST_INVALID")
        if type(self.key_id) is not str or KEY_ID_RE.fullmatch(self.key_id) is None:
            raise ReplayStoreError("REPLAY_KEY_ID_INVALID")
        _nonce_digest(self.nonce)
        if (
            type(self.expires_at_epoch_s) is not int
            or self.expires_at_epoch_s < 1
        ):
            raise ReplayStoreError("REPLAY_EXPIRY_INVALID")


@runtime_checkable
class ReplayReservationStore(Protocol):
    """Atomic, durable reservation boundary used by approval authorities."""

    def reserve_many(
        self,
        reservations: tuple[ReplayReservation, ...],
        *,
        now_epoch_s: int,
    ) -> None: ...


def _reservation_rows(
    reservations: tuple[ReplayReservation, ...],
    now_epoch_s: int,
) -> tuple[tuple[str, str, str, int], ...]:
    if not reservations:
        raise ReplayStoreError("REPLAY_RESERVATION_EMPTY")
    if type(now_epoch_s) is not int or now_epoch_s < 1:
        raise ReplayStoreError("REPLAY_CLOCK_INVALID")
    rows = tuple(
        (
            item.policy_sha256,
            item.key_id,
            _nonce_digest(item.nonce),
            item.expires_at_epoch_s,
        )
        for item in reservations
    )
    if len(set(row[:3] for row in rows)) != len(rows):
        raise ReplayStoreError("EVIDENCE_NONCE_DUPLICATE")
    return rows


class SQLiteReplayStore:
    """Reserve an evidence set in one SQLite transaction.

    Callers must complete every signature, subject, time and payload check before
    invoking ``reserve_many``.  A uniqueness conflict rolls back the entire set.
    """

    def __init__(self, database_path: Path) -> None:
        if not isinstance(database_path, Path) or database_path.name in {"", ".", ".."}:
            raise ReplayStoreError("REPLAY_DATABASE_PATH_INVALID")
        self._path = database_path
        self._prepare()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self._path,
            isolation_level=None,
            timeout=30.0,
        )
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    def _prepare(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            parent = self._path.parent.lstat()
            if self._path.parent.is_symlink() or not self._path.parent.is_dir():
                raise ReplayStoreError("REPLAY_DATABASE_PARENT_INVALID")
            if parent.st_mode & 0o022:
                raise ReplayStoreError("REPLAY_DATABASE_PARENT_PERMISSIONS_INVALID")
            if self._path.exists() and self._path.is_symlink():
                raise ReplayStoreError("REPLAY_DATABASE_PATH_INVALID")
            with self._connect() as connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS helper1_evidence_nonce (
                        policy_sha256 TEXT NOT NULL,
                        key_id TEXT NOT NULL,
                        nonce_sha256 TEXT NOT NULL,
                        expires_at_epoch_s INTEGER NOT NULL,
                        PRIMARY KEY (policy_sha256, key_id, nonce_sha256)
                    ) WITHOUT ROWID
                    """
                )
            os.chmod(self._path, 0o600)
        except ReplayStoreError:
            raise
        except (OSError, sqlite3.Error) as exc:
            raise ReplayStoreError("REPLAY_DATABASE_UNAVAILABLE") from exc

    @property
    def database_path(self) -> Path:
        return self._path

    def reserve_many(
        self,
        reservations: tuple[ReplayReservation, ...],
        *,
        now_epoch_s: int,
    ) -> None:
        rows = _reservation_rows(reservations, now_epoch_s)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "DELETE FROM helper1_evidence_nonce WHERE expires_at_epoch_s <= ?",
                (now_epoch_s,),
            )
            connection.executemany(
                """
                INSERT INTO helper1_evidence_nonce
                    (policy_sha256, key_id, nonce_sha256, expires_at_epoch_s)
                VALUES (?, ?, ?, ?)
                """,
                rows,
            )
            connection.execute("COMMIT")
        except sqlite3.IntegrityError as exc:
            connection.execute("ROLLBACK")
            raise ReplayStoreError("EVIDENCE_REPLAY_DETECTED") from exc
        except sqlite3.Error as exc:
            try:
                connection.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise ReplayStoreError("REPLAY_RESERVATION_FAILED") from exc
        finally:
            connection.close()


class PostgreSQLReplayStore:
    """Reserve approval nonces in one PostgreSQL transaction.

    The protected workflow supplies the DSN from an environment secret. The
    fixed primary key makes concurrent reservations across runners and process
    boundaries resolve to exactly one winner.
    """

    _CREATE_SQL = """
        CREATE TABLE IF NOT EXISTS helper1_evidence_nonce (
            policy_sha256 CHAR(64) NOT NULL,
            key_id VARCHAR(128) NOT NULL,
            nonce_sha256 CHAR(64) NOT NULL,
            expires_at_epoch_s BIGINT NOT NULL,
            PRIMARY KEY (policy_sha256, key_id, nonce_sha256)
        )
    """
    _DELETE_SQL = """
        DELETE FROM helper1_evidence_nonce WHERE expires_at_epoch_s <= %s
    """
    _INSERT_SQL = """
        INSERT INTO helper1_evidence_nonce
            (policy_sha256, key_id, nonce_sha256, expires_at_epoch_s)
        VALUES (%s, %s, %s, %s)
    """
    _ROUTING_QUERY_KEYS = frozenset({"host", "hostaddr", "service", "passfile"})
    _ROUTING_ENV_KEYS = (
        "PGHOST",
        "PGHOSTADDR",
        "PGPORT",
        "PGSERVICE",
        "PGSERVICEFILE",
    )
    _LOCAL_HOST_SUFFIXES = (".local", ".localhost", ".localdomain", ".internal")

    def __init__(
        self,
        dsn: str,
        *,
        connector: Callable[..., Any] | None = None,
        resolver: Callable[..., Any] | None = None,
    ) -> None:
        conninfo_to_dict, make_conninfo, default_connector = self._load_driver()
        self._dsn, self._pinned_endpoints = self._validate_dsn(
            dsn,
            conninfo_to_dict,
            make_conninfo,
            resolver or socket.getaddrinfo,
        )
        self._connector = connector or default_connector
        self._prepare()

    @classmethod
    def _validate_dsn(
        cls,
        dsn: str,
        conninfo_to_dict: Callable[[str], dict[str, str]],
        make_conninfo: Callable[..., str],
        resolver: Callable[..., Any],
    ) -> tuple[str, frozenset[tuple[str, str, int]]]:
        if (
            type(dsn) is not str
            or not (1 <= len(dsn) <= 4096)
            or any(ord(ch) < 32 for ch in dsn)
        ):
            raise ReplayStoreError("REPLAY_STORE_DSN_INVALID")
        try:
            uri = urlsplit(dsn)
            query = parse_qsl(uri.query, keep_blank_values=True, strict_parsing=True)
            query_keys = tuple(key.casefold() for key, _ in query)
            interpreted = conninfo_to_dict(dsn)
        except Exception as exc:
            raise ReplayStoreError("REPLAY_STORE_DSN_INVALID") from exc
        if (
            uri.scheme not in {"postgres", "postgresql"}
            or uri.path in {"", "/"}
            or uri.fragment
            or len(set(query_keys)) != len(query_keys)
            or cls._ROUTING_QUERY_KEYS.intersection(query_keys)
            or interpreted.get("sslmode") != "verify-full"
            or not interpreted.get("dbname")
            or any(interpreted.get(key) for key in cls._ROUTING_QUERY_KEYS - {"host"})
        ):
            raise ReplayStoreError("REPLAY_STORE_DSN_INVALID")
        hosts = cls._validate_remote_hosts(interpreted.get("host"))
        ports = cls._validate_ports(interpreted.get("port"), len(hosts))
        endpoints = cls._resolve_endpoints(hosts, ports, resolver)
        connection_values = dict(interpreted)
        connection_values["host"] = ",".join(item[0] for item in endpoints)
        connection_values["hostaddr"] = ",".join(item[1] for item in endpoints)
        connection_values["port"] = ",".join(str(item[2]) for item in endpoints)
        try:
            canonical_dsn = make_conninfo(**connection_values)
        except Exception as exc:
            raise ReplayStoreError("REPLAY_STORE_DSN_INVALID") from exc
        return canonical_dsn, frozenset(endpoints)

    @staticmethod
    def _load_driver() -> tuple[
        Callable[[str], dict[str, str]],
        Callable[..., str],
        Callable[..., Any],
    ]:
        try:
            from psycopg import connect
            from psycopg.conninfo import conninfo_to_dict, make_conninfo
        except (ImportError, OSError) as exc:
            raise ReplayStoreError("REPLAY_STORE_DRIVER_UNAVAILABLE") from exc
        return conninfo_to_dict, make_conninfo, connect

    @classmethod
    def _validate_remote_hosts(cls, raw_hosts: object) -> tuple[str, ...]:
        if type(raw_hosts) is not str:
            raise ReplayStoreError("REPLAY_STORE_DSN_INVALID")
        hosts = tuple(item.strip().rstrip(".").casefold() for item in raw_hosts.split(","))
        if not hosts or any(not item for item in hosts):
            raise ReplayStoreError("REPLAY_STORE_DSN_INVALID")
        for host in hosts:
            if host.startswith(("/", "@")):
                raise ReplayStoreError("REPLAY_STORE_ENDPOINT_FORBIDDEN")
            try:
                address = ipaddress.ip_address(host.strip("[]"))
            except ValueError:
                if (
                    "." not in host
                    or host == "localhost"
                    or host.endswith(cls._LOCAL_HOST_SUFFIXES)
                ):
                    raise ReplayStoreError("REPLAY_STORE_ENDPOINT_FORBIDDEN")
            else:
                if not address.is_global:
                    raise ReplayStoreError("REPLAY_STORE_ENDPOINT_FORBIDDEN")
        return hosts

    @staticmethod
    def _validate_ports(raw_ports: object, host_count: int) -> tuple[int, ...]:
        if raw_ports is None:
            values = ("5432",)
        elif type(raw_ports) is str:
            values = tuple(item.strip() for item in raw_ports.split(","))
        else:
            raise ReplayStoreError("REPLAY_STORE_DSN_INVALID")
        if len(values) == 1:
            values *= host_count
        if len(values) != host_count or any(not item.isascii() or not item.isdecimal() for item in values):
            raise ReplayStoreError("REPLAY_STORE_DSN_INVALID")
        ports = tuple(int(item) for item in values)
        if any(not 1 <= item <= 65535 for item in ports):
            raise ReplayStoreError("REPLAY_STORE_DSN_INVALID")
        return ports

    @classmethod
    def _resolve_endpoints(
        cls,
        hosts: tuple[str, ...],
        ports: tuple[int, ...],
        resolver: Callable[..., Any],
    ) -> tuple[tuple[str, str, int], ...]:
        endpoints: list[tuple[str, str, int]] = []
        for host, port in zip(hosts, ports, strict=True):
            try:
                literal = ipaddress.ip_address(host.strip("[]"))
            except ValueError:
                try:
                    answers = resolver(
                        host,
                        port,
                        family=socket.AF_UNSPEC,
                        type=socket.SOCK_STREAM,
                        proto=socket.IPPROTO_TCP,
                    )
                except (OSError, socket.gaierror) as exc:
                    raise ReplayStoreError("REPLAY_STORE_DNS_RESOLUTION_FAILED") from exc
                addresses: set[ipaddress.IPv4Address | ipaddress.IPv6Address] = set()
                try:
                    for answer in answers:
                        addresses.add(ipaddress.ip_address(answer[4][0]))
                except (IndexError, TypeError, ValueError) as exc:
                    raise ReplayStoreError("REPLAY_STORE_DNS_RESOLUTION_FAILED") from exc
                if not addresses:
                    raise ReplayStoreError("REPLAY_STORE_DNS_RESOLUTION_FAILED")
            else:
                addresses = {literal}
            if any(not address.is_global for address in addresses):
                raise ReplayStoreError("REPLAY_STORE_ENDPOINT_FORBIDDEN")
            for address in sorted(addresses, key=lambda item: (item.version, int(item))):
                endpoints.append((host, address.compressed, port))
        if not endpoints:
            raise ReplayStoreError("REPLAY_STORE_DNS_RESOLUTION_FAILED")
        return tuple(endpoints)

    @classmethod
    def _validate_routing_environment(cls) -> None:
        if any(os.environ.get(name) for name in cls._ROUTING_ENV_KEYS):
            raise ReplayStoreError("REPLAY_STORE_ROUTING_ENV_FORBIDDEN")

    def _validate_connected_endpoint(self, connection: Any) -> None:
        info = getattr(connection, "info", None)
        host = getattr(info, "host", None)
        hostaddr = getattr(info, "hostaddr", None)
        port = getattr(info, "port", None)
        try:
            normalized_hosts = self._validate_remote_hosts(host)
            if (
                len(normalized_hosts) != 1
                or type(hostaddr) is not str
                or type(port) not in {int, str}
                or not str(port).isascii()
                or not str(port).isdecimal()
            ):
                raise ReplayStoreError("REPLAY_STORE_ENDPOINT_FORBIDDEN")
            address = ipaddress.ip_address(hostaddr)
            endpoint = (normalized_hosts[0], address.compressed, int(port))
            if not address.is_global or endpoint not in self._pinned_endpoints:
                raise ReplayStoreError("REPLAY_STORE_ENDPOINT_FORBIDDEN")
        except ValueError as exc:
            raise ReplayStoreError("REPLAY_STORE_ENDPOINT_FORBIDDEN") from exc

    def _connect(self) -> Any:
        self._validate_routing_environment()
        try:
            connection = self._connector(self._dsn, connect_timeout=10)
        except Exception as exc:
            raise ReplayStoreError("REPLAY_STORE_CONNECTION_FAILED") from exc
        try:
            self._validate_connected_endpoint(connection)
        except ReplayStoreError:
            self._close(connection)
            raise
        return connection

    @staticmethod
    def _close(connection: Any, cursor: Any | None = None) -> None:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                pass
        try:
            connection.close()
        except Exception:
            pass

    def _prepare(self) -> None:
        connection = self._connect()
        cursor = None
        try:
            cursor = connection.cursor()
            cursor.execute(self._CREATE_SQL)
            connection.commit()
        except Exception as exc:
            try:
                connection.rollback()
            except Exception:
                pass
            raise ReplayStoreError("REPLAY_STORE_SCHEMA_FAILED") from exc
        finally:
            self._close(connection, cursor)

    def reserve_many(
        self,
        reservations: tuple[ReplayReservation, ...],
        *,
        now_epoch_s: int,
    ) -> None:
        rows = _reservation_rows(reservations, now_epoch_s)
        connection = self._connect()
        cursor = None
        try:
            cursor = connection.cursor()
            cursor.execute(self._DELETE_SQL, (now_epoch_s,))
            cursor.executemany(self._INSERT_SQL, rows)
            connection.commit()
        except Exception as exc:
            try:
                connection.rollback()
            except Exception:
                pass
            if getattr(exc, "sqlstate", None) == "23505":
                raise ReplayStoreError("EVIDENCE_REPLAY_DETECTED") from exc
            raise ReplayStoreError("REPLAY_RESERVATION_FAILED") from exc
        finally:
            self._close(connection, cursor)
