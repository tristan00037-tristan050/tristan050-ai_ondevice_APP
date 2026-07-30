"""Encrypted immutable Helper1 index generations with independent verification."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
import os
import stat
import struct
import uuid
from dataclasses import dataclass
from typing import Any, Mapping

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .contracts import (
    ArtifactRecord,
    AssetIdentity,
    EncoderIdentity,
    Helper1ContractError,
    IndexManifest,
    canonical_json,
    require_digest,
    require_uuid,
    sha256_bytes,
    validate_no_unknown_keys,
)
from .ingestion import Chunk
from .security import (
    Helper1SecurityError,
    KeyProvider,
    derive_subkey,
    open_regular_at,
    read_bounded_fd,
    safe_relative_path,
)

MAX_INDEX_ARTIFACT_BYTES = 8 * 1024 * 1024 * 1024
MAX_CHUNKS = 2_000_000
MAX_TERMS = 20_000_000
ENVELOPE_SCHEMA = "butler.helper1.aesgcm.v2"


class IndexStoreError(RuntimeError):
    pass


@dataclass(frozen=True)
class LoadedIndex:
    manifest: IndexManifest
    chunks: tuple[Chunk, ...]
    embeddings: tuple[tuple[float, ...], ...]
    lexical_index: Mapping[str, Any]


def _open_directory_at(root_fd: int, name: str) -> int:
    safe_relative_path(name)
    try:
        fd = os.open(
            name,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
            dir_fd=root_fd,
        )
    except OSError as exc:
        raise IndexStoreError("INDEX_DIRECTORY_OPEN_FAILED") from exc
    if not stat.S_ISDIR(os.fstat(fd).st_mode):
        os.close(fd)
        raise IndexStoreError("INDEX_DIRECTORY_INVALID")
    return fd


def _mkdir_at(root_fd: int, name: str) -> int:
    safe_relative_path(name)
    try:
        os.mkdir(name, mode=0o700, dir_fd=root_fd)
    except FileExistsError as exc:
        raise IndexStoreError("INDEX_GENERATION_ALREADY_EXISTS") from exc
    except OSError as exc:
        raise IndexStoreError("INDEX_DIRECTORY_CREATE_FAILED") from exc
    return _open_directory_at(root_fd, name)


def _write_new_file(directory_fd: int, name: str, payload: bytes) -> None:
    safe_relative_path(name)
    try:
        fd = os.open(
            name,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | os.O_NOFOLLOW
            | os.O_CLOEXEC,
            0o600,
            dir_fd=directory_fd,
        )
        try:
            offset = 0
            while offset < len(payload):
                written = os.write(fd, payload[offset:])
                if written <= 0:
                    raise IndexStoreError("INDEX_WRITE_FAILED")
                offset += written
            os.fsync(fd)
        finally:
            os.close(fd)
    except IndexStoreError:
        raise
    except OSError as exc:
        raise IndexStoreError("INDEX_WRITE_FAILED") from exc


def _read_file(directory_fd: int, name: str, maximum: int) -> bytes:
    fd = open_regular_at(directory_fd, name)
    try:
        return read_bounded_fd(fd, maximum=maximum)
    except Helper1SecurityError as exc:
        raise IndexStoreError(str(exc)) from exc
    finally:
        os.close(fd)


def _fsync_directory(fd: int) -> None:
    try:
        os.fsync(fd)
    except OSError as exc:
        raise IndexStoreError("INDEX_FSYNC_FAILED") from exc


def _remove_tree_at(root_fd: int, name: str) -> None:
    """Remove only a validated direct child used as an unpublished staging dir."""
    if not name.startswith(".stage-"):
        raise IndexStoreError("INDEX_CLEANUP_SCOPE_INVALID")
    directory_fd = _open_directory_at(root_fd, name)
    try:
        for entry in os.scandir(directory_fd):
            info = entry.stat(follow_symlinks=False)
            if stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
                raise IndexStoreError("INDEX_CLEANUP_ENTRY_INVALID")
            os.unlink(entry.name, dir_fd=directory_fd)
    finally:
        os.close(directory_fd)
    os.rmdir(name, dir_fd=root_fd)


def _aad(
    *,
    workspace_id: str,
    generation_id: str,
    role: str,
    encoder_sha256: str,
    policy_sha256: str,
    plaintext_bytes: int,
) -> bytes:
    return canonical_json(
        {
            "schema_version": ENVELOPE_SCHEMA,
            "workspace_id": workspace_id,
            "generation_id": generation_id,
            "role": role,
            "encoder_sha256": encoder_sha256,
            "policy_sha256": policy_sha256,
            "plaintext_bytes": plaintext_bytes,
        }
    )


def _encrypt_payload(key: bytes, aad: bytes, plaintext: bytes) -> bytes:
    if len(key) != 32:
        raise IndexStoreError("INDEX_KEY_INVALID")
    nonce = os.urandom(12)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, aad)
    return canonical_json(
        {
            "schema_version": ENVELOPE_SCHEMA,
            "nonce_b64": base64.b64encode(nonce).decode("ascii"),
            "ciphertext_b64": base64.b64encode(ciphertext).decode("ascii"),
            "aad_sha256": sha256_bytes(aad),
            "plaintext_bytes": len(plaintext),
        }
    )


def _decrypt_payload(key: bytes, aad: bytes, envelope_bytes: bytes) -> bytes:
    try:
        envelope = json.loads(envelope_bytes)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise IndexStoreError("INDEX_ENVELOPE_INVALID") from exc
    if not isinstance(envelope, dict):
        raise IndexStoreError("INDEX_ENVELOPE_INVALID")
    validate_no_unknown_keys(
        envelope,
        (
            "schema_version",
            "nonce_b64",
            "ciphertext_b64",
            "aad_sha256",
            "plaintext_bytes",
        ),
        "INDEX_ENVELOPE_UNKNOWN_FIELD",
    )
    if envelope.get("schema_version") != ENVELOPE_SCHEMA:
        raise IndexStoreError("INDEX_ENVELOPE_SCHEMA_INVALID")
    if envelope.get("aad_sha256") != sha256_bytes(aad):
        raise IndexStoreError("INDEX_ENVELOPE_AAD_MISMATCH")
    plaintext_bytes = envelope.get("plaintext_bytes")
    if (
        isinstance(plaintext_bytes, bool)
        or not isinstance(plaintext_bytes, int)
        or plaintext_bytes < 1
        or plaintext_bytes > MAX_INDEX_ARTIFACT_BYTES
    ):
        raise IndexStoreError("INDEX_ENVELOPE_SIZE_INVALID")
    try:
        nonce = base64.b64decode(envelope["nonce_b64"], validate=True)
        ciphertext = base64.b64decode(envelope["ciphertext_b64"], validate=True)
    except (KeyError, ValueError, TypeError) as exc:
        raise IndexStoreError("INDEX_ENVELOPE_ENCODING_INVALID") from exc
    if len(nonce) != 12:
        raise IndexStoreError("INDEX_ENVELOPE_NONCE_INVALID")
    try:
        plaintext = AESGCM(key).decrypt(nonce, ciphertext, aad)
    except Exception as exc:
        raise IndexStoreError("INDEX_DECRYPT_FAILED") from exc
    if len(plaintext) != plaintext_bytes:
        raise IndexStoreError("INDEX_PLAINTEXT_SIZE_MISMATCH")
    return plaintext


def _pack_embeddings(vectors: tuple[tuple[float, ...], ...], dimension: int) -> bytes:
    if not vectors or len(vectors) > MAX_CHUNKS:
        raise IndexStoreError("EMBEDDING_ROWS_INVALID")
    output = bytearray(b"H1F2")
    output.extend(struct.pack("<II", len(vectors), dimension))
    for vector in vectors:
        if len(vector) != dimension:
            raise IndexStoreError("EMBEDDING_DIMENSION_MISMATCH")
        for value in vector:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise IndexStoreError("EMBEDDING_VALUE_INVALID")
            number = float(value)
            if not math.isfinite(number):
                raise IndexStoreError("EMBEDDING_NONFINITE")
            output.extend(struct.pack("<f", number))
    return bytes(output)


def _unpack_embeddings(
    payload: bytes, expected_rows: int, expected_dimension: int
) -> tuple[tuple[float, ...], ...]:
    if len(payload) < 12 or payload[:4] != b"H1F2":
        raise IndexStoreError("EMBEDDING_FORMAT_INVALID")
    rows, dimension = struct.unpack("<II", payload[4:12])
    expected_bytes = 12 + rows * dimension * 4
    if (
        rows != expected_rows
        or dimension != expected_dimension
        or expected_bytes != len(payload)
    ):
        raise IndexStoreError("EMBEDDING_SHAPE_INVALID")
    values = struct.iter_unpack("<f", payload[12:])
    flat = [item[0] for item in values]
    if any(not math.isfinite(value) for value in flat):
        raise IndexStoreError("EMBEDDING_NONFINITE")
    return tuple(
        tuple(flat[offset : offset + dimension])
        for offset in range(0, len(flat), dimension)
    )


def _asset_from_dict(value: object) -> AssetIdentity:
    if not isinstance(value, dict):
        raise IndexStoreError("ENCODER_ASSET_INVALID")
    validate_no_unknown_keys(
        value,
        (
            "role",
            "model_id",
            "upstream_revision",
            "closure_manifest_sha256",
            "runtime_name",
            "runtime_version",
            "runtime_binary_sha256",
            "tokenizer_sha256",
        ),
        "ENCODER_ASSET_UNKNOWN_FIELD",
    )
    try:
        return AssetIdentity(**value)
    except (TypeError, Helper1ContractError) as exc:
        raise IndexStoreError(str(exc)) from exc


def _encoder_from_dict(value: object) -> EncoderIdentity:
    if not isinstance(value, dict):
        raise IndexStoreError("ENCODER_IDENTITY_INVALID")
    validate_no_unknown_keys(
        value,
        (
            "asset",
            "pooling",
            "normalize",
            "dimension",
            "max_length",
            "truncation_policy",
            "document_prefix_sha256",
            "query_prefix_sha256",
            "output_dtype",
        ),
        "ENCODER_IDENTITY_UNKNOWN_FIELD",
    )
    try:
        return EncoderIdentity(
            asset=_asset_from_dict(value.get("asset")),
            pooling=value.get("pooling"),  # type: ignore[arg-type]
            normalize=value.get("normalize"),  # type: ignore[arg-type]
            dimension=value.get("dimension"),  # type: ignore[arg-type]
            max_length=value.get("max_length"),  # type: ignore[arg-type]
            truncation_policy=value.get("truncation_policy"),  # type: ignore[arg-type]
            document_prefix_sha256=value.get("document_prefix_sha256"),  # type: ignore[arg-type]
            query_prefix_sha256=value.get("query_prefix_sha256"),  # type: ignore[arg-type]
            output_dtype=value.get("output_dtype"),  # type: ignore[arg-type]
        )
    except (TypeError, Helper1ContractError) as exc:
        raise IndexStoreError(str(exc)) from exc


def _manifest_from_dict(value: object) -> IndexManifest:
    if not isinstance(value, dict):
        raise IndexStoreError("INDEX_MANIFEST_INVALID")
    validate_no_unknown_keys(
        value,
        (
            "schema_version",
            "workspace_id",
            "generation_id",
            "previous_generation_id",
            "encoder",
            "lexical_tokenizer_sha256",
            "chunker_policy_sha256",
            "document_set_hmac_sha256",
            "policy_sha256",
            "chunk_count",
            "embedding_rows",
            "embedding_dimension",
            "lexical_term_count",
            "artifacts",
        ),
        "INDEX_MANIFEST_UNKNOWN_FIELD",
    )
    raw_artifacts = value.get("artifacts")
    if not isinstance(raw_artifacts, dict):
        raise IndexStoreError("INDEX_ARTIFACTS_INVALID")
    artifacts: dict[str, ArtifactRecord] = {}
    for role, record in raw_artifacts.items():
        if not isinstance(role, str) or not isinstance(record, dict):
            raise IndexStoreError("INDEX_ARTIFACT_INVALID")
        validate_no_unknown_keys(
            record, ("path", "bytes", "sha256"), "INDEX_ARTIFACT_UNKNOWN_FIELD"
        )
        try:
            artifacts[role] = ArtifactRecord(**record)
        except (TypeError, Helper1ContractError) as exc:
            raise IndexStoreError(str(exc)) from exc
    try:
        return IndexManifest(
            schema_version=value.get("schema_version"),  # type: ignore[arg-type]
            workspace_id=value.get("workspace_id"),  # type: ignore[arg-type]
            generation_id=value.get("generation_id"),  # type: ignore[arg-type]
            previous_generation_id=value.get("previous_generation_id"),  # type: ignore[arg-type]
            encoder=_encoder_from_dict(value.get("encoder")),
            lexical_tokenizer_sha256=value.get("lexical_tokenizer_sha256"),  # type: ignore[arg-type]
            chunker_policy_sha256=value.get("chunker_policy_sha256"),  # type: ignore[arg-type]
            document_set_hmac_sha256=value.get("document_set_hmac_sha256"),  # type: ignore[arg-type]
            policy_sha256=value.get("policy_sha256"),  # type: ignore[arg-type]
            chunk_count=value.get("chunk_count"),  # type: ignore[arg-type]
            embedding_rows=value.get("embedding_rows"),  # type: ignore[arg-type]
            embedding_dimension=value.get("embedding_dimension"),  # type: ignore[arg-type]
            lexical_term_count=value.get("lexical_term_count"),  # type: ignore[arg-type]
            artifacts=artifacts,
        )
    except (TypeError, Helper1ContractError) as exc:
        raise IndexStoreError(str(exc)) from exc


@dataclass
class EncryptedGenerationStore:
    root_fd: int
    key_provider: KeyProvider

    def __post_init__(self) -> None:
        info = os.fstat(self.root_fd)
        if not stat.S_ISDIR(info.st_mode):
            raise IndexStoreError("INDEX_ROOT_INVALID")

    def _signature(
        self, workspace_id: str, manifest_bytes: bytes
    ) -> tuple[str, bytes]:
        key_id, master = self.key_provider.key(workspace_id)
        key = derive_subkey(master, b"index-manifest-signing")
        signature = hmac.new(
            key, b"butler/helper1/index-manifest/v2\x00" + manifest_bytes, hashlib.sha256
        ).hexdigest()
        return key_id, canonical_json(
            {
                "schema_version": "butler.helper1.index-signature.v2",
                "key_id": key_id,
                "signature_sha256": signature,
            }
        )

    def publish(
        self,
        *,
        workspace_id: str,
        encoder: EncoderIdentity,
        chunks: tuple[Chunk, ...],
        embeddings: tuple[tuple[float, ...], ...],
        lexical_index: Mapping[str, Any],
        lexical_tokenizer_sha256: str,
        chunker_policy_sha256: str,
        document_set_hmac_sha256: str,
        policy_sha256: str,
        previous_generation_id: str | None = None,
    ) -> IndexManifest:
        require_uuid(workspace_id, "WORKSPACE_ID_INVALID")
        require_digest(lexical_tokenizer_sha256, "LEXICAL_TOKENIZER_INVALID")
        require_digest(chunker_policy_sha256, "CHUNKER_POLICY_INVALID")
        require_digest(document_set_hmac_sha256, "DOCUMENT_SET_HMAC_INVALID")
        require_digest(policy_sha256, "INDEX_POLICY_DIGEST_INVALID")
        if len(chunks) != len(embeddings):
            raise IndexStoreError("INDEX_COUNT_MISMATCH")
        generation_id = str(uuid.uuid4())
        stage_name = f".stage-{generation_id}"
        final_name = f"gen-{generation_id}"
        key_id, master = self.key_provider.key(workspace_id)
        del key_id
        key = derive_subkey(master, b"index-artifact-aead")
        plaintexts = {
            "chunks": canonical_json(
                {
                    "schema_version": "butler.helper1.chunks.v2",
                    "items": [chunk.to_dict() for chunk in chunks],
                }
            ),
            "embeddings": _pack_embeddings(embeddings, encoder.dimension),
            "lexical_index": canonical_json(lexical_index),
        }
        stage_fd = _mkdir_at(self.root_fd, stage_name)
        try:
            artifacts: dict[str, ArtifactRecord] = {}
            names = {
                "chunks": "chunks.enc",
                "embeddings": "embeddings.enc",
                "lexical_index": "lexical.enc",
            }
            for role in ("chunks", "embeddings", "lexical_index"):
                plaintext = plaintexts[role]
                aad = _aad(
                    workspace_id=workspace_id,
                    generation_id=generation_id,
                    role=role,
                    encoder_sha256=encoder.digest,
                    policy_sha256=policy_sha256,
                    plaintext_bytes=len(plaintext),
                )
                envelope = _encrypt_payload(key, aad, plaintext)
                name = names[role]
                _write_new_file(stage_fd, name, envelope)
                artifacts[role] = ArtifactRecord(
                    path=name, bytes=len(envelope), sha256=sha256_bytes(envelope)
                )
            terms = lexical_index.get("terms") if isinstance(lexical_index, dict) else None
            if not isinstance(terms, dict) or not terms or len(terms) > MAX_TERMS:
                raise IndexStoreError("LEXICAL_INDEX_INVALID")
            manifest = IndexManifest(
                workspace_id=workspace_id,
                generation_id=generation_id,
                previous_generation_id=previous_generation_id,
                encoder=encoder,
                lexical_tokenizer_sha256=lexical_tokenizer_sha256,
                chunker_policy_sha256=chunker_policy_sha256,
                document_set_hmac_sha256=document_set_hmac_sha256,
                policy_sha256=policy_sha256,
                chunk_count=len(chunks),
                embedding_rows=len(embeddings),
                embedding_dimension=encoder.dimension,
                lexical_term_count=len(terms),
                artifacts=artifacts,
            )
            manifest_bytes = canonical_json(manifest.to_dict())
            _write_new_file(stage_fd, "manifest.json", manifest_bytes)
            _, signature_bytes = self._signature(workspace_id, manifest_bytes)
            _write_new_file(stage_fd, "manifest.sig", signature_bytes)
            _fsync_directory(stage_fd)
        except Exception:
            os.close(stage_fd)
            _remove_tree_at(self.root_fd, stage_name)
            raise
        else:
            os.close(stage_fd)
        os.rename(
            stage_name,
            final_name,
            src_dir_fd=self.root_fd,
            dst_dir_fd=self.root_fd,
        )
        _fsync_directory(self.root_fd)
        verified = self.verify_generation(final_name)
        if verified.manifest.digest != manifest.digest:
            raise IndexStoreError("INDEX_POST_PUBLISH_VERIFY_FAILED")

        pointer_name = f".current-{generation_id}"
        _write_new_file(self.root_fd, pointer_name, (generation_id + "\n").encode("ascii"))
        os.replace(
            pointer_name,
            "CURRENT",
            src_dir_fd=self.root_fd,
            dst_dir_fd=self.root_fd,
        )
        _fsync_directory(self.root_fd)
        return manifest

    def current_generation_id(self) -> str:
        value = _read_file(self.root_fd, "CURRENT", 128)
        try:
            generation_id = value.decode("ascii").strip()
        except UnicodeDecodeError as exc:
            raise IndexStoreError("INDEX_POINTER_INVALID") from exc
        require_uuid(generation_id, "INDEX_POINTER_INVALID")
        return generation_id

    def verify_generation(self, generation_name: str | None = None) -> LoadedIndex:
        if generation_name is None:
            generation_name = f"gen-{self.current_generation_id()}"
        if not generation_name.startswith("gen-"):
            raise IndexStoreError("INDEX_GENERATION_NAME_INVALID")
        generation_id = generation_name[4:]
        require_uuid(generation_id, "INDEX_GENERATION_NAME_INVALID")
        generation_fd = _open_directory_at(self.root_fd, generation_name)
        try:
            manifest_bytes = _read_file(generation_fd, "manifest.json", 4 * 1024 * 1024)
            signature_bytes = _read_file(generation_fd, "manifest.sig", 4096)
            try:
                manifest_value = json.loads(manifest_bytes)
                signature_value = json.loads(signature_bytes)
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise IndexStoreError("INDEX_METADATA_INVALID") from exc
            manifest = _manifest_from_dict(manifest_value)
            if manifest.generation_id != generation_id:
                raise IndexStoreError("INDEX_GENERATION_ID_MISMATCH")
            validate_no_unknown_keys(
                signature_value,
                ("schema_version", "key_id", "signature_sha256"),
                "INDEX_SIGNATURE_UNKNOWN_FIELD",
            )
            key_id, master = self.key_provider.key(manifest.workspace_id)
            signature_key = derive_subkey(master, b"index-manifest-signing")
            key = derive_subkey(master, b"index-artifact-aead")
            if (
                signature_value.get("schema_version")
                != "butler.helper1.index-signature.v2"
                or signature_value.get("key_id") != key_id
            ):
                raise IndexStoreError("INDEX_SIGNATURE_IDENTITY_INVALID")
            signature = signature_value.get("signature_sha256")
            require_digest(signature, "INDEX_SIGNATURE_INVALID")
            expected = hmac.new(
                signature_key,
                b"butler/helper1/index-manifest/v2\x00" + manifest_bytes,
                hashlib.sha256,
            ).hexdigest()
            if not hmac.compare_digest(signature, expected):
                raise IndexStoreError("INDEX_SIGNATURE_INVALID")

            plaintexts: dict[str, bytes] = {}
            for role, record in manifest.artifacts.items():
                envelope = _read_file(
                    generation_fd, record.path, MAX_INDEX_ARTIFACT_BYTES
                )
                if len(envelope) != record.bytes or not hmac.compare_digest(
                    sha256_bytes(envelope), record.sha256
                ):
                    raise IndexStoreError("INDEX_ARTIFACT_DIGEST_MISMATCH")
                try:
                    envelope_value = json.loads(envelope)
                    plaintext_bytes = envelope_value["plaintext_bytes"]
                except (json.JSONDecodeError, KeyError, TypeError) as exc:
                    raise IndexStoreError("INDEX_ENVELOPE_INVALID") from exc
                if isinstance(plaintext_bytes, bool) or not isinstance(
                    plaintext_bytes, int
                ):
                    raise IndexStoreError("INDEX_ENVELOPE_SIZE_INVALID")
                aad = _aad(
                    workspace_id=manifest.workspace_id,
                    generation_id=manifest.generation_id,
                    role=role,
                    encoder_sha256=manifest.encoder.digest,
                    policy_sha256=manifest.policy_sha256,
                    plaintext_bytes=plaintext_bytes,
                )
                plaintexts[role] = _decrypt_payload(key, aad, envelope)
        finally:
            os.close(generation_fd)

        try:
            chunk_value = json.loads(plaintexts["chunks"])
            lexical_value = json.loads(plaintexts["lexical_index"])
        except (json.JSONDecodeError, UnicodeDecodeError, KeyError) as exc:
            raise IndexStoreError("INDEX_PLAINTEXT_INVALID") from exc
        if (
            not isinstance(chunk_value, dict)
            or set(chunk_value) != {"schema_version", "items"}
            or chunk_value.get("schema_version") != "butler.helper1.chunks.v2"
            or not isinstance(chunk_value.get("items"), list)
        ):
            raise IndexStoreError("CHUNK_FORMAT_INVALID")
        chunks: list[Chunk] = []
        for item in chunk_value["items"]:
            if not isinstance(item, dict):
                raise IndexStoreError("CHUNK_RECORD_INVALID")
            validate_no_unknown_keys(
                item,
                ("chunk_id", "source_id", "text", "ordinal", "content_sha256"),
                "CHUNK_RECORD_UNKNOWN_FIELD",
            )
            try:
                chunk = Chunk(**item)
            except (TypeError, ValueError) as exc:
                raise IndexStoreError("CHUNK_RECORD_INVALID") from exc
            if chunk.content_sha256 != sha256_bytes(chunk.text.encode("utf-8")):
                raise IndexStoreError("CHUNK_DIGEST_MISMATCH")
            chunks.append(chunk)
        if len(chunks) != manifest.chunk_count:
            raise IndexStoreError("CHUNK_COUNT_MISMATCH")
        if len({chunk.chunk_id for chunk in chunks}) != len(chunks):
            raise IndexStoreError("CHUNK_ID_DUPLICATE")
        embeddings = _unpack_embeddings(
            plaintexts["embeddings"],
            manifest.embedding_rows,
            manifest.embedding_dimension,
        )
        if not isinstance(lexical_value, dict):
            raise IndexStoreError("LEXICAL_INDEX_INVALID")
        terms = lexical_value.get("terms")
        if not isinstance(terms, dict) or len(terms) != manifest.lexical_term_count:
            raise IndexStoreError("LEXICAL_TERM_COUNT_MISMATCH")
        return LoadedIndex(
            manifest=manifest,
            chunks=tuple(chunks),
            embeddings=embeddings,
            lexical_index=lexical_value,
        )
