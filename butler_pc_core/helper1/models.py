"""Descriptor-bound BGE-M3 and isolated native Qwen3 execution adapters."""
from __future__ import annotations

import hashlib
import json
import math
import os
import stat
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .contracts import (
    AssetIdentity,
    Claim,
    EncoderIdentity,
    canonical_json,
    require_digest,
    sha256_bytes,
)
from .security import VerifiedAssetClosure, read_bounded_fd

MAX_GENERATOR_OUTPUT_BYTES = 2 * 1024 * 1024


class ModelRuntimeError(RuntimeError):
    pass


def _token_value(value: object) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict) and isinstance(value.get("content"), str):
        return value["content"]
    return None


@dataclass
class DescriptorBgeM3Encoder:
    """Load BGE-M3 from manifest-verified bytes without reopening asset paths."""

    closure: VerifiedAssetClosure
    _identity: EncoderIdentity
    device: str | None = None
    _model: Any = field(default=None, init=False, repr=False)
    _tokenizer: Any = field(default=None, init=False, repr=False)
    _torch: Any = field(default=None, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def __post_init__(self) -> None:
        if self._identity.asset.role != "helper1_embed":
            raise ModelRuntimeError("EMBEDDER_ROLE_INVALID")
        if self._identity.asset.closure_manifest_sha256 != self.closure.manifest_sha256:
            raise ModelRuntimeError("EMBEDDER_CLOSURE_IDENTITY_MISMATCH")

    @property
    def identity(self) -> EncoderIdentity:
        return self._identity

    def _load(self) -> None:
        if self._model is not None:
            return
        if not self.closure._verified:
            raise ModelRuntimeError("EMBEDDER_CLOSURE_NOT_VERIFIED")
        try:
            import torch
            from safetensors.torch import load as load_safetensors
            from tokenizers import Tokenizer
            from transformers import AutoConfig, AutoModel, PreTrainedTokenizerFast
        except ImportError as exc:
            raise ModelRuntimeError("EMBEDDER_RUNTIME_MISSING") from exc
        try:
            config_value = json.loads(
                self.closure.read_verified("config.json", 4 * 1024 * 1024)
            )
            tokenizer_text = self.closure.read_verified(
                "tokenizer.json", 256 * 1024 * 1024
            ).decode("utf-8")
            tokenizer_config = json.loads(
                self.closure.read_verified("tokenizer_config.json", 4 * 1024 * 1024)
            )
        except (KeyError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ModelRuntimeError("EMBEDDER_METADATA_INVALID") from exc
        if not isinstance(config_value, dict) or not isinstance(tokenizer_config, dict):
            raise ModelRuntimeError("EMBEDDER_METADATA_INVALID")
        model_type = config_value.get("model_type")
        if not isinstance(model_type, str) or not model_type:
            raise ModelRuntimeError("EMBEDDER_MODEL_TYPE_INVALID")
        config_kwargs = dict(config_value)
        config_kwargs.pop("model_type", None)
        try:
            config = AutoConfig.for_model(model_type, **config_kwargs)
            model = AutoModel.from_config(config)
            tokenizer_object = Tokenizer.from_str(tokenizer_text)
            token_kwargs = {
                key: value
                for key in (
                    "model_max_length",
                    "padding_side",
                    "truncation_side",
                    "clean_up_tokenization_spaces",
                )
                if (value := tokenizer_config.get(key)) is not None
            }
            for key in (
                "bos_token",
                "eos_token",
                "unk_token",
                "sep_token",
                "pad_token",
                "cls_token",
                "mask_token",
            ):
                value = _token_value(tokenizer_config.get(key))
                if value is not None:
                    token_kwargs[key] = value
            tokenizer = PreTrainedTokenizerFast(
                tokenizer_object=tokenizer_object, **token_kwargs
            )
        except Exception as exc:
            raise ModelRuntimeError("EMBEDDER_CONSTRUCTION_FAILED") from exc
        weight_files = sorted(
            path for path in self.closure.files if path.endswith(".safetensors")
        )
        if not weight_files:
            raise ModelRuntimeError("EMBEDDER_WEIGHTS_MISSING")
        state: dict[str, Any] = {}
        try:
            for relative in weight_files:
                shard = load_safetensors(
                    self.closure.read_verified(relative, 4 * 1024 * 1024 * 1024)
                )
                overlap = set(state).intersection(shard)
                if overlap:
                    raise ModelRuntimeError("EMBEDDER_WEIGHT_KEY_DUPLICATE")
                state.update(shard)
            missing, unexpected = model.load_state_dict(state, strict=False)
        except ModelRuntimeError:
            raise
        except Exception as exc:
            raise ModelRuntimeError("EMBEDDER_WEIGHTS_LOAD_FAILED") from exc
        if missing or unexpected:
            raise ModelRuntimeError("EMBEDDER_WEIGHT_KEYS_MISMATCH")
        selected_device = self.device
        if selected_device is None:
            selected_device = "mps" if torch.backends.mps.is_available() else "cpu"
        try:
            model.eval()
            model.to(selected_device)
        except Exception as exc:
            raise ModelRuntimeError("EMBEDDER_DEVICE_FAILED") from exc
        self._torch = torch
        self._model = model
        self._tokenizer = tokenizer
        self.device = selected_device

    def _encode(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        if not texts or any(not isinstance(text, str) or not text for text in texts):
            raise ModelRuntimeError("EMBEDDER_INPUT_INVALID")
        with self._lock:
            self._load()
            assert self._tokenizer is not None and self._model is not None
            truncation = self.identity.truncation_policy != "reject"
            try:
                if not truncation:
                    lengths = self._tokenizer(
                        list(texts), add_special_tokens=True, truncation=False
                    )["input_ids"]
                    if any(len(value) > self.identity.max_length for value in lengths):
                        raise ModelRuntimeError("EMBEDDER_INPUT_TOO_LONG")
                batch = self._tokenizer(
                    list(texts),
                    padding=True,
                    truncation=truncation,
                    max_length=self.identity.max_length,
                    return_tensors="pt",
                )
                batch = {key: value.to(self.device) for key, value in batch.items()}
                with self._torch.inference_mode():
                    hidden = self._model(**batch).last_hidden_state
                    if self.identity.pooling == "cls":
                        pooled = hidden[:, 0]
                    elif self.identity.pooling == "mean":
                        mask = batch["attention_mask"].unsqueeze(-1)
                        pooled = (hidden * mask).sum(1) / mask.sum(1).clamp(min=1)
                    else:
                        last = batch["attention_mask"].sum(1) - 1
                        pooled = hidden[
                            self._torch.arange(hidden.shape[0], device=hidden.device),
                            last,
                        ]
                    if self.identity.normalize:
                        pooled = self._torch.nn.functional.normalize(pooled, p=2, dim=1)
                    values = pooled.to(dtype=self._torch.float32, device="cpu").tolist()
            except ModelRuntimeError:
                raise
            except Exception as exc:
                raise ModelRuntimeError("EMBEDDER_INFERENCE_FAILED") from exc
        vectors = tuple(tuple(float(value) for value in row) for row in values)
        if any(
            len(row) != self.identity.dimension
            or any(not math.isfinite(value) for value in row)
            for row in vectors
        ):
            raise ModelRuntimeError("EMBEDDER_OUTPUT_INVALID")
        return vectors

    def encode_documents(
        self, texts: tuple[str, ...]
    ) -> tuple[tuple[float, ...], ...]:
        return self._encode(texts)

    def encode_query(self, text: str) -> tuple[float, ...]:
        return self._encode((text,))[0]


@dataclass(frozen=True)
class GeneratedDraft:
    answer: str
    claims: tuple[Claim, ...]


@dataclass
class NativeQwen3Generator:
    """One process per request; native worker consumes the already-open GGUF FD.

    The worker contract requires llama.cpp's
    ``llama_model_load_from_file_ptr(FILE*, params)``.  A path-based worker is
    rejected by protocol and cannot claim the Helper1 answer role.
    """

    model_closure: VerifiedAssetClosure
    model_relative_path: str
    asset_identity: AssetIdentity
    runner_path: str
    chat_template_sha256: str
    timeout_seconds: int = 120

    def __post_init__(self) -> None:
        if self.asset_identity.role != "helper1_answer":
            raise ModelRuntimeError("GENERATOR_ROLE_INVALID")
        if (
            self.asset_identity.closure_manifest_sha256
            != self.model_closure.manifest_sha256
        ):
            raise ModelRuntimeError("GENERATOR_CLOSURE_IDENTITY_MISMATCH")
        require_digest(self.chat_template_sha256, "GENERATOR_CHAT_TEMPLATE_INVALID")
        if (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, int)
            or not 1 <= self.timeout_seconds <= 600
        ):
            raise ModelRuntimeError("GENERATOR_TIMEOUT_INVALID")
        if not os.path.isabs(self.runner_path):
            raise ModelRuntimeError("GENERATOR_RUNNER_PATH_INVALID")
        try:
            info = os.lstat(self.runner_path)
        except OSError as exc:
            raise ModelRuntimeError("GENERATOR_RUNNER_MISSING") from exc
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
            or not info.st_mode & stat.S_IXUSR
        ):
            raise ModelRuntimeError("GENERATOR_RUNNER_UNTRUSTED")
        digest = hashlib.sha256()
        try:
            with open(self.runner_path, "rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
        except OSError as exc:
            raise ModelRuntimeError("GENERATOR_RUNNER_READ_FAILED") from exc
        if digest.hexdigest() != self.asset_identity.runtime_binary_sha256:
            raise ModelRuntimeError("GENERATOR_RUNNER_DIGEST_MISMATCH")

    @property
    def identity_sha256(self) -> str:
        return sha256_bytes(
            canonical_json(
                {
                    "asset": self.asset_identity.to_dict(),
                    "chat_template_sha256": self.chat_template_sha256,
                    "isolation": "one-process-per-request-v1",
                    "model_loader": "llama_model_load_from_file_ptr",
                }
            )
        )

    def generate(self, prompt: str, *, max_tokens: int = 1024) -> GeneratedDraft:
        if not isinstance(prompt, str) or not prompt or len(prompt) > 2_000_000:
            raise ModelRuntimeError("GENERATOR_PROMPT_INVALID")
        if isinstance(max_tokens, bool) or not 1 <= max_tokens <= 4096:
            raise ModelRuntimeError("GENERATOR_TOKEN_LIMIT_INVALID")
        model_fd = self.model_closure.open_verified(self.model_relative_path)
        request = canonical_json(
            {
                "schema_version": "butler.helper1.native-request.v1",
                "model_fd": model_fd,
                "model_identity_sha256": self.identity_sha256,
                "prompt": prompt,
                "max_tokens": max_tokens,
                "temperature": 0.1,
                "thinking": False,
                "json_output": True,
            }
        )
        try:
            completed = subprocess.run(
                [self.runner_path, "--protocol", "helper1-v1"],
                input=request,
                capture_output=True,
                check=False,
                timeout=self.timeout_seconds,
                pass_fds=(model_fd,),
                env={
                    "PATH": "/usr/bin:/bin",
                    "LANG": "C",
                    "LC_ALL": "C",
                    "BUTLER_NETWORK_ALLOWED": "0",
                },
            )
        except subprocess.TimeoutExpired as exc:
            raise ModelRuntimeError("GENERATOR_TIMEOUT") from exc
        except OSError as exc:
            raise ModelRuntimeError("GENERATOR_SPAWN_FAILED") from exc
        finally:
            os.close(model_fd)
        if completed.returncode != 0:
            raise ModelRuntimeError("GENERATOR_FAILED")
        if completed.stderr:
            raise ModelRuntimeError("GENERATOR_STDERR_FORBIDDEN")
        if not completed.stdout or len(completed.stdout) > MAX_GENERATOR_OUTPUT_BYTES:
            raise ModelRuntimeError("GENERATOR_OUTPUT_SIZE_INVALID")
        def reject_duplicate_fields(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            output: dict[str, Any] = {}
            for key, item in pairs:
                if key in output:
                    raise ModelRuntimeError("GENERATOR_OUTPUT_DUPLICATE_FIELD")
                output[key] = item
            return output

        try:
            value = json.loads(
                completed.stdout,
                object_pairs_hook=reject_duplicate_fields,
                parse_constant=lambda _value: (_ for _ in ()).throw(
                    ModelRuntimeError("GENERATOR_OUTPUT_NONFINITE")
                ),
            )
        except ModelRuntimeError:
            raise
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ModelRuntimeError("GENERATOR_OUTPUT_INVALID") from exc
        if not isinstance(value, dict) or set(value) != {
            "schema_version",
            "answer",
            "claims",
            "model_identity_sha256",
            "loader",
            "thinking",
            "kv_disposed",
        }:
            raise ModelRuntimeError("GENERATOR_OUTPUT_FIELDS_INVALID")
        if (
            value.get("schema_version") != "butler.helper1.native-response.v1"
            or value.get("model_identity_sha256") != self.identity_sha256
            or value.get("loader") != "llama_model_load_from_file_ptr"
            or value.get("thinking") is not False
            or value.get("kv_disposed") is not True
            or not isinstance(value.get("answer"), str)
            or not value["answer"]
            or not isinstance(value.get("claims"), list)
            or not value["claims"]
        ):
            raise ModelRuntimeError("GENERATOR_OUTPUT_CONTRACT_INVALID")
        claims = []
        for raw in value["claims"]:
            if not isinstance(raw, dict) or set(raw) != {
                "claim_id",
                "text",
                "chunk_id",
                "evidence_start",
                "evidence_end",
            }:
                raise ModelRuntimeError("GENERATOR_CLAIM_INVALID")
            try:
                claims.append(Claim(**raw))
            except (TypeError, ValueError) as exc:
                raise ModelRuntimeError("GENERATOR_CLAIM_INVALID") from exc
        return GeneratedDraft(answer=value["answer"], claims=tuple(claims))
