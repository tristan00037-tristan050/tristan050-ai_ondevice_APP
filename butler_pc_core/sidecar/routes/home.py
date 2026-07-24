from __future__ import annotations

import json
import math
import os
import re
import uuid
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError as PydanticValidationError

from butler_pc_core.company_profile.storage import CompanyProfileStore, ProfileLoadError
from butler_pc_core.home.store import (
    ConflictError,
    HomeStore,
    MigrationConflict,
    NotFoundError,
    ReadOnlyError,
    StorageUnavailableError,
    ValidationError,
    command_was_replayed,
)
from butler_pc_core.firstscreen_runtime_trust import (
    RuntimeTrustError,
    read_secure_regular_file,
)
from butler_pc_core.firstscreen_trust import TrustVerificationError, build_context_digest, strict_json_loads


MAX_BODY_BYTES = 2 * 1024 * 1024
_ETAG = re.compile(r'^"v([1-9][0-9]*)"$')
router = APIRouter()
_STORE: HomeStore | None = None


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class MessagePayload(StrictModel):
    id: str = Field(min_length=1, max_length=128)
    role: Literal["user", "butler"]
    content: str
    timestamp: str
    source: Literal["factpack", "llm"] | None = None
    fact_id: str | None = None
    score: float | None = None


class LegacyConversation(StrictModel):
    id: str = Field(min_length=1, max_length=128)
    folder_id: str | None = None
    title: str = Field(min_length=1, max_length=256)
    title_is_custom: bool
    created_at: str
    updated_at: str
    messages: list[MessagePayload] = Field(max_length=10_000)


class MigrationRequest(StrictModel):
    schema_version: Literal["butler.home.migration.request.v2"]
    migration_id: str = Field(pattern=r"^[A-Za-z0-9_.:-]{1,64}$")
    conversations: list[LegacyConversation] = Field(max_length=10_000)


class FolderCreateRequest(StrictModel):
    name: str = Field(min_length=1, max_length=128)
    parent_id: str | None = None


class FolderRenameRequest(StrictModel):
    name: str = Field(min_length=1, max_length=128)


class ConversationRenameRequest(StrictModel):
    title: str = Field(min_length=1, max_length=256)


class ConversationCommand(StrictModel):
    id: str = Field(min_length=1, max_length=128)
    folder_id: str | None
    title: str = Field(min_length=1, max_length=256)
    title_is_custom: bool
    created_at: str
    updated_at: str


class UserTurnRequest(StrictModel):
    conversation: ConversationCommand
    message: MessagePayload


class AssistantTurnRequest(StrictModel):
    turn_id: str
    model_request_id: str
    message: MessagePayload


class TerminalRequest(StrictModel):
    conversation_id: str = Field(min_length=1, max_length=128)
    turn_id: str
    state: Literal["FAILED", "CANCELLED", "TIMED_OUT"]
    error_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,63}$")


class MoveRequest(StrictModel):
    folder_id: str = Field(min_length=1, max_length=128)


class RetentionRequest(StrictModel):
    retention_days: int = Field(ge=1, le=3650)


class ProfileReassignmentRequest(StrictModel):
    profile_id: str | None
    confirmed: Literal[True]


class MirrorRepairRequest(StrictModel):
    confirmed: Literal[True]


def initialize_home_store(*, bootstrap_new_install: bool | None = None) -> HomeStore:
    global _STORE
    if _STORE is None:
        _STORE = HomeStore(bootstrap_new_install=bootstrap_new_install)
    return _STORE


def shutdown_home_store() -> None:
    global _STORE
    store, _STORE = _STORE, None
    if store is not None:
        store.flush()
        store.close()


def get_home_store() -> HomeStore:
    return initialize_home_store()


def _active_profile_id() -> str | None:
    try:
        entry = CompanyProfileStore().load_active_index()
    except ProfileLoadError:
        return None
    return entry.profile_id if entry and entry.status == "ACTIVE" else None


def _strong_version(if_match: str | None) -> int:
    match = _ETAG.fullmatch(if_match or "")
    if not match:
        raise HTTPException(428, detail={"code": "STRONG_IF_MATCH_REQUIRED"})
    return int(match.group(1))


def _uuid_header(value: str | None, name: str) -> str:
    try:
        return str(uuid.UUID(value or ""))
    except ValueError as exc:
        raise HTTPException(428, detail={"code": f"{name}_UUID_REQUIRED"}) from exc


def _mutation_context(
    request: Request, x_request_id: str | None, idempotency_key: str | None,
) -> tuple[str, str, str, str]:
    request_id = _uuid_header(x_request_id, "X_REQUEST_ID")
    idempotency = _uuid_header(idempotency_key, "IDEMPOTENCY_KEY")
    actor = getattr(request.state, "capability_actor_id", None)
    session_digest = getattr(request.state, "capability_session_digest", None)
    if not isinstance(actor, str) or not isinstance(session_digest, str):
        raise HTTPException(401, detail={"code": "CAPABILITY_SESSION_REQUIRED"})
    return request_id, idempotency, actor, session_digest


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _parse_integer(raw: str) -> int:
    if raw == "-0":
        raise ValueError("NEGATIVE_ZERO")
    return int(raw)


def _parse_float(raw: str) -> float:
    value = float(raw)
    if not math.isfinite(value) or (value == 0 and raw.lstrip().startswith("-")):
        raise ValueError("NON_CANONICAL_NUMBER")
    return value


async def _payload(request: Request, model: type[StrictModel]) -> StrictModel:
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_BODY_BYTES:
                raise HTTPException(413, detail={"code": "BODY_TOO_LARGE"})
        except ValueError as exc:
            raise HTTPException(400, detail={"code": "INVALID_CONTENT_LENGTH"}) from exc
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > MAX_BODY_BYTES:
            raise HTTPException(413, detail={"code": "BODY_TOO_LARGE"})
        chunks.append(chunk)
    try:
        value = json.loads(
            b"".join(chunks), object_pairs_hook=_reject_duplicate_keys,
            parse_int=_parse_integer, parse_float=_parse_float,
            parse_constant=lambda _constant: (_ for _ in ()).throw(ValueError("NON_FINITE_JSON_NUMBER")),
        )
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(400, detail={"code": "INVALID_JSON"}) from exc
    except ValueError as exc:
        code = "DUPLICATE_JSON_KEY" if str(exc) == "DUPLICATE_JSON_KEY" else "INVALID_JSON"
        raise HTTPException(400, detail={"code": code}) from exc
    try:
        return model.model_validate(value)
    except PydanticValidationError as exc:
        raise HTTPException(422, detail={"code": "SCHEMA_VALIDATION_FAILED", "field_count": len(exc.errors())}) from exc


def _raise_store(exc: Exception) -> None:
    if isinstance(exc, MigrationConflict):
        raise HTTPException(409, detail={"code": str(exc), "receipt": exc.receipt}) from exc
    if isinstance(exc, ValidationError):
        raise HTTPException(422, detail={"code": str(exc)}) from exc
    if isinstance(exc, ConflictError):
        raise HTTPException(409, detail={"code": str(exc)}) from exc
    if isinstance(exc, NotFoundError):
        raise HTTPException(404, detail={"code": str(exc)}) from exc
    if isinstance(exc, ReadOnlyError):
        raise HTTPException(423, detail={"code": str(exc), "startup": get_home_store().startup_status()}) from exc
    if isinstance(exc, StorageUnavailableError):
        raise HTTPException(503, detail={"code": str(exc)}) from exc
    raise exc


def _set_replay_header(response: Response) -> None:
    response.headers["Idempotency-Replayed"] = "true" if command_was_replayed() else "false"


@router.get("/v1/home/bootstrap-status")
async def bootstrap_status() -> dict[str, Any]:
    return get_home_store().startup_status()


@router.get("/v1/home/snapshot")
async def snapshot(
    limit: int = Query(default=50, ge=1, le=100), cursor: str | None = Query(default=None),
    include_trash: bool = Query(default=False), profile_id: str | None = Query(default=None),
) -> dict[str, Any]:
    try:
        return get_home_store().snapshot(limit=limit, cursor=cursor, include_trash=include_trash, profile_id=profile_id)
    except Exception as exc:
        _raise_store(exc)
        raise


@router.get("/v1/home/conversations/{conversation_id}/messages")
async def messages(
    conversation_id: str, after_sequence: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=100),
) -> dict[str, Any]:
    try:
        return get_home_store().messages(conversation_id, after_sequence=after_sequence, limit=limit)
    except Exception as exc:
        _raise_store(exc)
        raise


@router.get("/v1/home/search")
async def search(
    q: str = Query(min_length=1, max_length=256), limit: int = Query(default=50, ge=1, le=100),
    profile_id: str | None = Query(default=None),
) -> dict[str, Any]:
    try:
        return get_home_store().search(q, limit=limit, profile_id=profile_id)
    except Exception as exc:
        _raise_store(exc)
        raise


@router.post("/v1/home/migrations/legacy-conversations")
async def migrate(
    request: Request, response: Response, x_request_id: str | None = Header(default=None),
    idempotency_key: str | None = Header(default=None),
) -> dict[str, Any]:
    body = await _payload(request, MigrationRequest)
    assert isinstance(body, MigrationRequest)
    request_id, idempotency, actor, session = _mutation_context(request, x_request_id, idempotency_key)
    try:
        conversations = [item.model_dump(exclude_none=True) for item in body.conversations]
        receipt = get_home_store().migrate_legacy(
            conversations, migration_id=body.migration_id, request_id=request_id,
            idempotency_key=idempotency, actor=actor, session_digest=session,
        )
        _set_replay_header(response)
        return {"receipt": receipt, "snapshot": get_home_store().snapshot()}
    except Exception as exc:
        _raise_store(exc)
        raise


@router.post("/v1/home/folders", status_code=201)
async def create_folder(
    request: Request, response: Response, x_request_id: str | None = Header(default=None),
    idempotency_key: str | None = Header(default=None),
) -> dict[str, Any]:
    body = await _payload(request, FolderCreateRequest)
    assert isinstance(body, FolderCreateRequest)
    request_id, idempotency, actor, session = _mutation_context(request, x_request_id, idempotency_key)
    try:
        result = get_home_store().create_folder(body.name, parent_id=body.parent_id, request_id=request_id, idempotency_key=idempotency, actor=actor, session_digest=session)
        _set_replay_header(response)
        return result
    except Exception as exc:
        _raise_store(exc)
        raise


@router.patch("/v1/home/folders/{folder_id}")
async def rename_folder(
    folder_id: str, request: Request, response: Response,
    if_match: str | None = Header(default=None), x_request_id: str | None = Header(default=None),
    idempotency_key: str | None = Header(default=None),
) -> dict[str, Any]:
    body = await _payload(request, FolderRenameRequest)
    assert isinstance(body, FolderRenameRequest)
    request_id, idempotency, actor, session = _mutation_context(request, x_request_id, idempotency_key)
    try:
        result = get_home_store().rename_folder(folder_id, body.name, _strong_version(if_match), request_id=request_id, idempotency_key=idempotency, actor=actor, session_digest=session)
        response.headers["ETag"] = f'"v{result["version"]}"'
        _set_replay_header(response)
        return result
    except Exception as exc:
        _raise_store(exc)
        raise


@router.delete("/v1/home/folders/{folder_id}")
async def delete_folder(
    folder_id: str, request: Request, response: Response, if_match: str | None = Header(default=None),
    x_request_id: str | None = Header(default=None), idempotency_key: str | None = Header(default=None),
) -> dict[str, Any]:
    request_id, idempotency, actor, session = _mutation_context(request, x_request_id, idempotency_key)
    try:
        result = get_home_store().delete_folder(folder_id, _strong_version(if_match), request_id=request_id, idempotency_key=idempotency, actor=actor, session_digest=session)
        _set_replay_header(response)
        return result
    except Exception as exc:
        _raise_store(exc)
        raise


@router.post("/v1/home/conversations/{conversation_id}/turns/user")
async def accept_user_turn(
    conversation_id: str, request: Request, response: Response,
    if_match: str | None = Header(default=None), x_request_id: str | None = Header(default=None),
    idempotency_key: str | None = Header(default=None),
) -> dict[str, Any]:
    body = await _payload(request, UserTurnRequest)
    assert isinstance(body, UserTurnRequest)
    if body.conversation.id != conversation_id:
        raise HTTPException(422, detail={"code": "CONVERSATION_ID_MISMATCH"})
    request_id, idempotency, actor, session = _mutation_context(request, x_request_id, idempotency_key)
    try:
        result = get_home_store().accept_user_turn(
            body.conversation.model_dump(), body.message.model_dump(exclude_none=True),
            business_profile_id=_active_profile_id(), expected_version=_strong_version(if_match) if if_match else None,
            request_id=request_id, idempotency_key=idempotency, actor=actor, session_digest=session,
        )
        response.headers["ETag"] = f'"v{result["conversation_version"]}"'
        _set_replay_header(response)
        return result
    except Exception as exc:
        _raise_store(exc)
        raise


@router.post("/v1/home/conversations/{conversation_id}/turns/assistant")
async def assistant_turn(
    conversation_id: str, request: Request, response: Response,
    if_match: str | None = Header(default=None), x_request_id: str | None = Header(default=None),
    idempotency_key: str | None = Header(default=None),
) -> dict[str, Any]:
    body = await _payload(request, AssistantTurnRequest)
    assert isinstance(body, AssistantTurnRequest)
    request_id, idempotency, actor, session = _mutation_context(request, x_request_id, idempotency_key)
    try:
        expected_version = _strong_version(if_match)
        result = get_home_store().append_assistant_turn(
            conversation_id, body.message.model_dump(exclude_none=True), expected_version,
            turn_id=body.turn_id, model_request_id=body.model_request_id, request_id=request_id,
            idempotency_key=idempotency, actor=actor, session_digest=session,
        )
        response.headers["ETag"] = f'"v{expected_version + 1}"'
        _set_replay_header(response)
        return result
    except Exception as exc:
        _raise_store(exc)
        raise


@router.post("/v1/home/model-requests/{model_request_id}/terminal")
async def terminal(
    model_request_id: str, request: Request, response: Response,
    x_request_id: str | None = Header(default=None), idempotency_key: str | None = Header(default=None),
) -> dict[str, Any]:
    body = await _payload(request, TerminalRequest)
    assert isinstance(body, TerminalRequest)
    request_id, idempotency, actor, session = _mutation_context(request, x_request_id, idempotency_key)
    try:
        result = get_home_store().record_terminal(
            body.conversation_id, body.state, body.error_code, turn_id=body.turn_id,
            model_request_id=model_request_id, request_id=request_id, idempotency_key=idempotency,
            actor=actor, session_digest=session,
        )
        _set_replay_header(response)
        return result
    except Exception as exc:
        _raise_store(exc)
        raise


def _conversation_context(request: Request, x_request_id: str | None, idempotency_key: str | None) -> tuple[str, str, str, str]:
    return _mutation_context(request, x_request_id, idempotency_key)


@router.patch("/v1/home/conversations/{conversation_id}")
async def rename_conversation(
    conversation_id: str, request: Request, response: Response,
    if_match: str | None = Header(default=None), x_request_id: str | None = Header(default=None),
    idempotency_key: str | None = Header(default=None),
) -> dict[str, Any]:
    body = await _payload(request, ConversationRenameRequest)
    assert isinstance(body, ConversationRenameRequest)
    context = _conversation_context(request, x_request_id, idempotency_key)
    try:
        result = get_home_store().rename_conversation(conversation_id, body.title, _strong_version(if_match), request_id=context[0], idempotency_key=context[1], actor=context[2], session_digest=context[3])
        response.headers["ETag"] = f'"v{result["version"]}"'
        _set_replay_header(response)
        return result
    except Exception as exc:
        _raise_store(exc)
        raise


@router.post("/v1/home/conversations/{conversation_id}/move")
async def move(
    conversation_id: str, request: Request, response: Response,
    if_match: str | None = Header(default=None), x_request_id: str | None = Header(default=None),
    idempotency_key: str | None = Header(default=None),
) -> dict[str, Any]:
    body = await _payload(request, MoveRequest)
    assert isinstance(body, MoveRequest)
    context = _conversation_context(request, x_request_id, idempotency_key)
    try:
        result = get_home_store().move(conversation_id, body.folder_id, _strong_version(if_match), request_id=context[0], idempotency_key=context[1], actor=context[2], session_digest=context[3])
        response.headers["ETag"] = f'"v{result["version"]}"'
        _set_replay_header(response)
        return result
    except Exception as exc:
        _raise_store(exc)
        raise


@router.delete("/v1/home/conversations/{conversation_id}")
async def trash(
    conversation_id: str, request: Request, response: Response,
    if_match: str | None = Header(default=None), x_request_id: str | None = Header(default=None),
    idempotency_key: str | None = Header(default=None),
) -> dict[str, Any]:
    context = _conversation_context(request, x_request_id, idempotency_key)
    try:
        result = get_home_store().trash(conversation_id, _strong_version(if_match), request_id=context[0], idempotency_key=context[1], actor=context[2], session_digest=context[3])
        response.headers["ETag"] = f'"v{result["version"]}"'
        _set_replay_header(response)
        return result
    except Exception as exc:
        _raise_store(exc)
        raise


@router.post("/v1/home/conversations/{conversation_id}/restore")
async def restore(
    conversation_id: str, request: Request, response: Response,
    if_match: str | None = Header(default=None), x_request_id: str | None = Header(default=None),
    idempotency_key: str | None = Header(default=None),
) -> dict[str, Any]:
    body = await _payload(request, MoveRequest)
    assert isinstance(body, MoveRequest)
    context = _conversation_context(request, x_request_id, idempotency_key)
    try:
        result = get_home_store().restore(conversation_id, body.folder_id, _strong_version(if_match), request_id=context[0], idempotency_key=context[1], actor=context[2], session_digest=context[3])
        response.headers["ETag"] = f'"v{result["version"]}"'
        _set_replay_header(response)
        return result
    except Exception as exc:
        _raise_store(exc)
        raise


@router.delete("/v1/home/trash/{conversation_id}")
async def permanently_delete(
    conversation_id: str, request: Request, response: Response, if_match: str | None = Header(default=None),
    x_permanent_delete: str | None = Header(default=None), x_request_id: str | None = Header(default=None),
    idempotency_key: str | None = Header(default=None),
) -> dict[str, Any]:
    if x_permanent_delete != "confirm":
        raise HTTPException(428, detail={"code": "PERMANENT_DELETE_CONFIRMATION_REQUIRED"})
    context = _conversation_context(request, x_request_id, idempotency_key)
    try:
        result = get_home_store().purge(conversation_id, _strong_version(if_match), request_id=context[0], idempotency_key=context[1], actor=context[2], session_digest=context[3])
        _set_replay_header(response)
        return result
    except Exception as exc:
        _raise_store(exc)
        raise


@router.post("/v1/home/trash/purge-expired")
async def purge_expired(
    request: Request, response: Response, x_permanent_delete: str | None = Header(default=None),
    x_request_id: str | None = Header(default=None), idempotency_key: str | None = Header(default=None),
) -> dict[str, Any]:
    if x_permanent_delete != "confirm-retention":
        raise HTTPException(428, detail={"code": "RETENTION_DELETE_CONFIRMATION_REQUIRED"})
    body = await _payload(request, RetentionRequest)
    assert isinstance(body, RetentionRequest)
    context = _conversation_context(request, x_request_id, idempotency_key)
    try:
        result = get_home_store().purge_expired_trash(body.retention_days, request_id=context[0], idempotency_key=context[1], actor=context[2], session_digest=context[3])
        _set_replay_header(response)
        return result
    except Exception as exc:
        _raise_store(exc)
        raise


@router.post("/v1/home/conversations/{conversation_id}/profile")
async def reassign_profile(
    conversation_id: str, request: Request, response: Response,
    if_match: str | None = Header(default=None), x_request_id: str | None = Header(default=None),
    idempotency_key: str | None = Header(default=None),
) -> dict[str, Any]:
    body = await _payload(request, ProfileReassignmentRequest)
    assert isinstance(body, ProfileReassignmentRequest)
    context = _conversation_context(request, x_request_id, idempotency_key)
    try:
        result = get_home_store().reassign_profile(conversation_id, body.profile_id, _strong_version(if_match), request_id=context[0], idempotency_key=context[1], actor=context[2], session_digest=context[3])
        response.headers["ETag"] = f'"v{result["version"]}"'
        _set_replay_header(response)
        return result
    except Exception as exc:
        _raise_store(exc)
        raise


@router.post("/v1/home/workspace-mirror/repair")
async def repair_workspace_mirror(
    request: Request, x_request_id: str | None = Header(default=None),
    idempotency_key: str | None = Header(default=None),
) -> dict[str, Any]:
    body = await _payload(request, MirrorRepairRequest)
    assert isinstance(body, MirrorRepairRequest)
    context = _conversation_context(request, x_request_id, idempotency_key)
    try:
        return get_home_store().repair_workspace_mirror(confirmed=body.confirmed, request_id=context[0], idempotency_key=context[1], actor=context[2], session_digest=context[3])
    except Exception as exc:
        _raise_store(exc)
        raise


@router.get("/v1/home/integrity")
async def integrity() -> dict[str, Any]:
    try:
        return get_home_store().integrity_status()
    except Exception as exc:
        _raise_store(exc)
        raise


@router.get("/v1/home/runtime-status")
async def runtime_status() -> dict[str, Any]:
    return get_home_store().runtime_status()


def _trust_input(name: str, maximum: int = 1024 * 1024 * 1024) -> bytes:
    raw = os.environ.get(name)
    if not raw:
        raise RuntimeTrustError("TRUST_RUNTIME_NOT_CONFIGURED")
    return read_secure_regular_file(Path(raw), maximum=maximum)


@router.get("/v1/home/runtime-trust-candidate")
async def runtime_trust_candidate() -> dict[str, Any]:
    """Return public candidate bytes; only native code may decide or persist."""
    try:
        root = _trust_input("BUTLER_FIRSTSCREEN_ROOT_PATH", 256 * 1024)
        revocations = _trust_input("BUTLER_FIRSTSCREEN_REVOCATIONS_PATH", 256 * 1024)
        decision = _trust_input("BUTLER_FIRSTSCREEN_RISK_DECISION_PATH", 256 * 1024)
        release = _trust_input("BUTLER_FIRSTSCREEN_RELEASE_SUBJECTS_PATH", 256 * 1024)
        context = strict_json_loads(_trust_input("BUTLER_BUILD_CONTEXT_PATH", 64 * 1024), maximum=64 * 1024)
        return {
            "schema_version": "butler.firstscreen.trust-candidate.v2",
            "environment": os.environ.get("BUTLER_FIRSTSCREEN_ENVIRONMENT", "development"),
            "root_json": root.decode("utf-8", errors="strict"),
            "revocations_json": revocations.decode("utf-8", errors="strict"),
            "decision_json": decision.decode("utf-8", errors="strict"),
            "release_subjects_json": release.decode("utf-8", errors="strict"),
            "source_commit_oid": context["commit_oid"],
            "source_tree_oid": context["tree_oid"],
            "native_build_identity_digest": build_context_digest(context),
            "runtime_activation_allowed": False,
        }
    except (KeyError, OSError, UnicodeError, RuntimeTrustError, TrustVerificationError):
        raise HTTPException(423, detail={"code": "RUNTIME_TRUST_BLOCKED"})
