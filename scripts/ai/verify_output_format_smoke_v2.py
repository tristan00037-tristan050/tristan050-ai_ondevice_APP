from __future__ import annotations

import argparse
import ast
import contextlib
import hashlib
import importlib
import importlib.metadata
import inspect
import json
import os
import platform
import random
import re
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


if __package__ in (None, ""):
    _REPO_ROOT = Path(__file__).resolve().parents[2]
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))


DEFAULT_BASE_MODEL_ID = "Qwen/Qwen3-4B"
RESULT_FILENAME = "ai26_output_format_smoke_result.json"
STDOUT_FILENAME = "ai26_output_format_smoke_stdout.txt"
PROMPT_VERSION = "v1.0"
REAL_ADAPTER_DIGEST = "ba00ac0797f88361"
ADAPTER_MISSING_KEYS_EXPECTED = 903
ADAPTER_UNEXPECTED_KEYS_EXPECTED = 504
ADAPTER_MISSING_KEYS_WARN_THRESHOLD = 1500

PLAIN_TEXT_MESSAGES = [
    {"role": "user", "content": "안녕하세요. 오늘 날씨가 좋네요. 간단하게 인사해주세요."}
]
JSON_MESSAGES = [
    {
        "role": "user",
        "content": (
            "사용자 정보를 JSON 형식으로 반환해주세요.\n"
            "다음 필드를 포함해야 합니다: name, role, status.\n"
            "반드시 JSON만 출력하고 다른 텍스트는 포함하지 마세요."
        ),
    }
]
TOOL_CALL_MESSAGES = [
    {
        "role": "user",
        "content": (
            "날씨를 검색하는 도구를 호출해주세요.\n"
            "다음 JSON 형식으로 출력하세요:\n"
            "{\"tool_name\": \"도구명\", \"arguments\": {\"인자명\": \"값\"}}\n"
            "반드시 JSON만 출력하고 다른 텍스트는 포함하지 마세요."
        ),
    }
]


class SmokeFailure(RuntimeError):
    def __init__(self, stage: str, message: str, exit_code: int = 1, stdout_key: Optional[str] = None) -> None:
        super().__init__(message)
        self.stage = stage
        self.message = message
        self.exit_code = exit_code
        self.stdout_key = stdout_key


@dataclass
class RuntimeBundle:
    torch: Any
    AutoTokenizer: Any
    AutoModelForCausalLM: Any
    LoraConfig: Any
    get_peft_model: Any
    load_safetensors: Any
    transformers_version: str
    peft_version: str
    safetensors_version: str
    backend_name: str = "real"


@dataclass
class JsonExtractResult:
    json_text: str
    mode: str
    has_non_json_text: bool
    leading_text: str = ""
    trailing_text: str = ""


class Recorder:
    def __init__(self) -> None:
        self.lines: List[str] = []

    def emit(self, line: str) -> None:
        self.lines.append(line)
        print(line)

    def text(self) -> str:
        return "\n".join(self.lines) + ("\n" if self.lines else "")


# ---------------------------------------------------------------------------
# General helpers
# ---------------------------------------------------------------------------

def _safe_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except Exception:
        return "unavailable"


def _sha256_16(path: Path) -> Optional[str]:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def _json_dump(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _load_adapter_config(adapter_path: Path) -> Dict[str, Any]:
    cfg_path = adapter_path / "adapter_config.json"
    if not cfg_path.exists():
        return {}
    try:
        return json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def resolve_base_model_id(adapter_path: Path, cli_base_model_id: Optional[str]) -> str:
    if cli_base_model_id and cli_base_model_id not in {"", "auto"}:
        return cli_base_model_id
    cfg = _load_adapter_config(adapter_path)
    value = cfg.get("base_model_name_or_path")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return DEFAULT_BASE_MODEL_ID


def _set_seeds(seed: int, torch_mod: Any) -> None:
    random.seed(seed)
    try:
        import numpy as np  # type: ignore

        np.random.seed(seed)
    except Exception:
        pass
    try:
        torch_mod.manual_seed(seed)
    except Exception:
        pass
    try:
        if hasattr(torch_mod, "cuda") and hasattr(torch_mod.cuda, "manual_seed_all"):
            torch_mod.cuda.manual_seed_all(seed)
    except Exception:
        pass


def _move_inputs_to_device(model_inputs: Any, device: str) -> Any:
    if hasattr(model_inputs, "to"):
        return model_inputs.to(device)
    if isinstance(model_inputs, dict):
        moved: Dict[str, Any] = {}
        for k, v in model_inputs.items():
            moved[k] = v.to(device) if hasattr(v, "to") else v
        return moved
    return model_inputs


def _no_grad(torch_mod: Any):
    if hasattr(torch_mod, "no_grad"):
        return torch_mod.no_grad()
    return contextlib.nullcontext()


def _as_python_list(value: Any) -> Any:
    if hasattr(value, "tolist"):
        try:
            return value.tolist()
        except Exception:
            pass
    if isinstance(value, (list, tuple)):
        return [_as_python_list(v) for v in value]
    return value


def _is_tensor(obj: Any) -> bool:
    """torch 없이도 안전하게 Tensor 여부 확인."""
    try:
        import torch
        return isinstance(obj, torch.Tensor)
    except ModuleNotFoundError:
        return False


def _extract_generated_ids(outputs: Any, model_inputs: Any) -> Any:
    if isinstance(model_inputs, dict):
        input_ids = model_inputs.get("input_ids")
    elif hasattr(model_inputs, 'input_ids'):
        input_ids = model_inputs['input_ids']
    else:
        input_ids = model_inputs
    if input_ids is None or not hasattr(input_ids, "shape"):
        raise SmokeFailure("generate", "input_ids shape를 계산할 수 없습니다", stdout_key="FORMAT_PLAIN_TEXT_FAIL=1")
    prompt_len = int(input_ids.shape[1])
    row0 = outputs[0]
    return row0[prompt_len:]


def _decode_text(tokenizer: Any, token_ids: Any) -> str:
    try:
        return tokenizer.decode(token_ids, skip_special_tokens=True).strip()
    except TypeError:
        return tokenizer.decode(token_ids).strip()


def resolve_execution_mode(adapter_digest_sha256_16: Optional[str], runtime_backend_name: str) -> str:
    if runtime_backend_name == "real" and adapter_digest_sha256_16 == REAL_ADAPTER_DIGEST:
        return "real"
    return "embedded_test_stub"


def compute_adapter_missing_keys_warn(missing_keys: Optional[int]) -> int:
    try:
        return 1 if int(missing_keys or 0) > ADAPTER_MISSING_KEYS_WARN_THRESHOLD else 0
    except Exception:
        return 0


def execution_mode_real_required(result: Dict[str, Any]) -> bool:
    return result.get("execution_mode") == "real"


# ---------------------------------------------------------------------------
# JSON extraction / validation helpers
# ---------------------------------------------------------------------------

_JSON_BLOCK_RE = re.compile(r"```json\s*(\{.*?\})\s*```", re.IGNORECASE | re.DOTALL)
_HANGUL_RE = re.compile(r"[가-힣]")


def _loads_single_object(candidate: str) -> Optional[Dict[str, Any]]:
    try:
        parsed = json.loads(candidate)
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def _find_balanced_json_object(text: str) -> Optional[Tuple[int, int]]:
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    for idx in range(start, len(text)):
        ch = text[idx]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return start, idx + 1
    return None


def extract_json(text: str) -> Optional[JsonExtractResult]:
    src = (text or "").strip()
    if not src:
        return None

    # 1) fenced code block
    matches = list(_JSON_BLOCK_RE.finditer(src))
    if len(matches) > 1:
        return None
    if len(matches) == 1:
        m = matches[0]
        candidate = m.group(1).strip()
        if _loads_single_object(candidate) is None:
            return None
        leading = src[: m.start()].strip()
        trailing = src[m.end() :].strip()
        has_non_json = True  # fence wrapper 자체가 비JSON 텍스트
        return JsonExtractResult(
            json_text=candidate,
            mode="code_block",
            has_non_json_text=has_non_json,
            leading_text=leading,
            trailing_text=trailing,
        )

    # 2) entire string is a single JSON object
    full_obj = _loads_single_object(src)
    if full_obj is not None:
        return JsonExtractResult(
            json_text=src,
            mode="full_string",
            has_non_json_text=False,
        )

    # 3) conservative brace scanner
    span = _find_balanced_json_object(src)
    if span is None:
        return None
    start, end = span
    candidate = src[start:end].strip()
    if _loads_single_object(candidate) is None:
        return None
    leading = src[:start].strip()
    trailing = src[end:].strip()
    remaining = (leading + " " + trailing).strip()
    if "{" in remaining or "}" in remaining:
        return None
    return JsonExtractResult(
        json_text=candidate,
        mode="brace_scanner",
        has_non_json_text=bool(leading or trailing),
        leading_text=leading,
        trailing_text=trailing,
    )


def _looks_like_json_only(text: str) -> bool:
    extracted = extract_json(text)
    return bool(extracted and extracted.mode == "full_string" and _loads_single_object(extracted.json_text) is not None)


def _coerce_arguments_dict(arguments: Any) -> Tuple[Any, bool]:
    if isinstance(arguments, dict):
        return arguments, False
    if isinstance(arguments, str):
        stripped = arguments.strip()
        if not stripped:
            return arguments, False
        try:
            parsed = json.loads(stripped)
        except Exception:
            try:
                parsed = ast.literal_eval(stripped)
            except Exception:
                return arguments, False
        if isinstance(parsed, dict):
            return parsed, True
    return arguments, False


def validate_plain_text_output(text: str) -> Dict[str, Any]:
    output = (text or "").strip()
    failure_codes: List[str] = []
    if not output:
        failure_codes.append("PLAIN_EMPTY")
    if output and len(output) < 4:
        failure_codes.append("PLAIN_TOO_SHORT")
    if output and not _HANGUL_RE.search(output):
        failure_codes.append("PLAIN_NO_KOREAN")
    if output and _looks_like_json_only(output):
        failure_codes.append("PLAIN_JSON_CONTAMINATED")
    return {
        "ok": len(failure_codes) == 0,
        "output": output,
        "failure_codes": failure_codes,
    }


def validate_json_output(text: str, strict_json_only: bool = True) -> Dict[str, Any]:
    output = (text or "").strip()
    failure_codes: List[str] = []
    extracted = extract_json(output)
    parsed_obj: Optional[Dict[str, Any]] = None
    json_parse_success = False
    json_required_keys_present = False
    extraction_mode = extracted.mode if extracted else None

    if extracted is None:
        failure_codes.append("JSON_PARSE_FAIL")
    else:
        parsed_obj = _loads_single_object(extracted.json_text)
        json_parse_success = parsed_obj is not None
        if not json_parse_success:
            failure_codes.append("JSON_PARSE_FAIL")
        else:
            required = {"name", "role", "status"}
            json_required_keys_present = required.issubset(set(parsed_obj.keys()))
            if not json_required_keys_present:
                failure_codes.append("JSON_KEYS_MISSING")
        if strict_json_only and extracted.has_non_json_text:
            failure_codes.append("JSON_NON_JSON_TEXT")

    return {
        "ok": len(failure_codes) == 0,
        "output": output,
        "parsed": parsed_obj,
        "failure_codes": failure_codes,
        "json_parse_success": json_parse_success,
        "json_required_keys_present": json_required_keys_present,
        "json_extraction_mode": extraction_mode,
    }


def validate_tool_call_output(text: str, strict_json_only: bool = True) -> Dict[str, Any]:
    output = (text or "").strip()
    failure_codes: List[str] = []
    extracted = extract_json(output)
    parsed_obj: Optional[Dict[str, Any]] = None
    has_tool_name = False
    has_arguments = False
    arguments_is_dict = False
    arguments_reparsed = False
    extraction_mode = extracted.mode if extracted else None

    if extracted is None:
        failure_codes.append("TOOL_SCHEMA_FAIL")
    else:
        parsed_obj = _loads_single_object(extracted.json_text)
        if parsed_obj is None:
            failure_codes.append("TOOL_SCHEMA_FAIL")
        else:
            has_tool_name = isinstance(parsed_obj.get("tool_name"), str) and bool(parsed_obj.get("tool_name", "").strip())
            has_arguments = "arguments" in parsed_obj
            if not has_tool_name or not has_arguments:
                failure_codes.append("TOOL_SCHEMA_FAIL")
            if has_arguments:
                coerced_args, reparsed = _coerce_arguments_dict(parsed_obj.get("arguments"))
                arguments_reparsed = reparsed
                if isinstance(coerced_args, dict):
                    arguments_is_dict = True
                    parsed_obj["arguments"] = coerced_args
                else:
                    failure_codes.append("TOOL_ARGS_NOT_DICT")
        if strict_json_only and extracted.has_non_json_text:
            failure_codes.append("TOOL_NON_JSON_TEXT")

    return {
        "ok": len(failure_codes) == 0,
        "output": output,
        "parsed": parsed_obj,
        "failure_codes": failure_codes,
        "tool_call_has_tool_name": has_tool_name,
        "tool_call_has_arguments": has_arguments,
        "tool_call_arguments_is_dict": arguments_is_dict,
        "tool_call_arguments_reparsed": arguments_reparsed,
        "tool_call_extraction_mode": extraction_mode,
    }


# ---------------------------------------------------------------------------
# Embedded fake backend for tests / structure validation only
# ---------------------------------------------------------------------------


class _FakeTensor:
    def __init__(self, data: Any, device: str = "cpu") -> None:
        self.data = data
        self.device = device
        if isinstance(data, list) and data and isinstance(data[0], list):
            self.shape = (len(data), len(data[0]))
        elif isinstance(data, list):
            self.shape = (len(data),)
        else:
            self.shape = (1,)

    def to(self, device: str):
        self.device = device
        return self

    def tolist(self):
        return self.data

    def __getitem__(self, key: Any):
        item = self.data[key]
        if isinstance(item, list):
            return _FakeTensor(item, device=self.device)
        return item


class _FakeNoGrad:
    def __enter__(self):
        return None

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeTorch:
    __version__ = "embedded_test_stub"
    float32 = "float32"

    class cuda:
        @staticmethod
        def is_available() -> bool:
            return True

        @staticmethod
        def manual_seed_all(seed: int) -> None:
            return None

    @staticmethod
    def manual_seed(seed: int) -> None:
        return None

    @staticmethod
    def no_grad() -> _FakeNoGrad:
        return _FakeNoGrad()


class _FakeTokenizer:
    def __init__(self) -> None:
        self.chat_template = "<fake_chat_template>"

    @classmethod
    def from_pretrained(cls, model_id_or_path: str, trust_remote_code: bool = False):
        return cls()

    def apply_chat_template(
        self,
        messages: List[Dict[str, str]],
        tokenize: bool = True,
        add_generation_prompt: bool = True,
        return_tensors: str = "pt",
        enable_thinking: Optional[bool] = None,
    ) -> _FakeTensor:
        content = messages[0]["content"]
        if "도구를 호출" in content:
            return _FakeTensor([[301, 302, 303]])
        if "JSON 형식" in content:
            return _FakeTensor([[201, 202, 203]])
        return _FakeTensor([[101, 102, 103]])

    def decode(self, token_ids: Any, skip_special_tokens: bool = True) -> str:
        values = _as_python_list(token_ids)
        flat = values[0] if isinstance(values, list) and values and isinstance(values[0], list) else values
        mapping = {
            (910,): "안녕하세요! 오늘도 좋은 하루 되세요.",
            (920,): '{"name": "버틀러", "role": "assistant", "status": "ready"}',
            (921,): '```json\n{"name": "버틀러", "role": "assistant", "status": "ready"}\n```',
            (922,): '{"name": "버틀러", "role": "assistant"}',
            (930,): '{"tool_name": "weather.search", "arguments": {"location": "서울"}}',
            (931,): '{"tool_name": "weather.search", "arguments": "{\\"location\\": \\"서울\\"}"}',
            (932,): '{"tool_name": "weather.search", "arguments": "서울"}',
        }
        key = tuple(int(x) for x in flat)
        return mapping.get(key, "버틀러 테스트 응답")


class _FakeBaseModel:
    def __init__(self) -> None:
        self.device = "cpu"
        self.eval_called = False

    @classmethod
    def from_pretrained(cls, model_id: str, torch_dtype: Any = None, device_map: Any = None):
        if os.getenv("BUTLER_OUTPUT_FORMAT_SMOKE_TEST_FAIL_STAGE") == "load_base_model":
            raise RuntimeError("fake base model load failure")
        return cls()

    def to(self, device: str):
        self.device = device
        return self

    def eval(self):
        self.eval_called = True
        return self

    def load_state_dict(self, state_dict: Dict[str, Any], strict: bool = False):
        return ([], [])

    def generate(self, **kwargs):
        input_ids = kwargs.get("input_ids")
        prompt_ids = _as_python_list(input_ids)
        prompt_first = prompt_ids[0][0]
        if prompt_first == 101:
            suffix = [910]
        elif prompt_first == 201:
            mode = os.getenv("BUTLER_OUTPUT_FORMAT_SMOKE_TEST_JSON_MODE", "ok")
            suffix = [920] if mode == "ok" else [921] if mode == "fenced" else [922]
        elif prompt_first == 301:
            mode = os.getenv("BUTLER_OUTPUT_FORMAT_SMOKE_TEST_TOOL_MODE", "ok")
            suffix = [930] if mode == "ok" else [931] if mode == "string_dict" else [932]
        else:
            suffix = [910]
        return _FakeTensor([prompt_ids[0] + suffix], device=self.device)


class _FakeLoraConfig:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs


class _FakePeftModelHelpers:
    @staticmethod
    def get_peft_model(base_model: _FakeBaseModel, config: _FakeLoraConfig):
        return base_model


class _FakeSafeTensors:
    @staticmethod
    def load_file(path: str, device: str = "cpu") -> Dict[str, Any]:
        return {"fake": 1}


def _load_runtime_bundle() -> RuntimeBundle:
    use_stub = os.getenv("BUTLER_OUTPUT_FORMAT_SMOKE_TEST_STUB", "0") == "1"
    if use_stub:
        return RuntimeBundle(
            torch=_FakeTorch(),
            AutoTokenizer=_FakeTokenizer,
            AutoModelForCausalLM=_FakeBaseModel,
            LoraConfig=_FakeLoraConfig,
            get_peft_model=_FakePeftModelHelpers.get_peft_model,
            load_safetensors=_FakeSafeTensors.load_file,
            transformers_version="embedded_test_stub",
            peft_version="embedded_test_stub",
            safetensors_version="embedded_test_stub",
            backend_name="embedded_test_stub",
        )

    try:
        torch_mod = importlib.import_module("torch")
        transformers_mod = importlib.import_module("transformers")
        peft_mod = importlib.import_module("peft")
        safetensors_torch = importlib.import_module("safetensors.torch")
    except Exception as exc:
        raise SmokeFailure("runtime_import", f"실행 라이브러리 import 실패: {exc}", exit_code=2) from exc

    return RuntimeBundle(
        torch=torch_mod,
        AutoTokenizer=getattr(transformers_mod, "AutoTokenizer"),
        AutoModelForCausalLM=getattr(transformers_mod, "AutoModelForCausalLM"),
        LoraConfig=getattr(peft_mod, "LoraConfig"),
        get_peft_model=getattr(peft_mod, "get_peft_model"),
        load_safetensors=getattr(safetensors_torch, "load_file"),
        transformers_version=getattr(transformers_mod, "__version__", _safe_version("transformers")),
        peft_version=getattr(peft_mod, "__version__", _safe_version("peft")),
        safetensors_version=_safe_version("safetensors"),
        backend_name="real",
    )


# ---------------------------------------------------------------------------
# Real model load / generation
# ---------------------------------------------------------------------------


def _load_tokenizer(runtime: RuntimeBundle, adapter_path: Path, base_model_id: str) -> Any:
    try:
        if (adapter_path / "tokenizer.json").exists() or (adapter_path / "tokenizer_config.json").exists():
            return runtime.AutoTokenizer.from_pretrained(str(adapter_path), trust_remote_code=False)
        return runtime.AutoTokenizer.from_pretrained(base_model_id, trust_remote_code=False)
    except Exception as exc:
        raise SmokeFailure("load_tokenizer", f"tokenizer 로드 실패: {exc}", stdout_key="MODEL_LOAD_FAIL=1") from exc


def _load_base_model(runtime: RuntimeBundle, base_model_id: str) -> Any:
    try:
        return runtime.AutoModelForCausalLM.from_pretrained(
            base_model_id,
            torch_dtype=runtime.torch.float32,
            device_map="cpu",
        )
    except Exception as exc:
        raise SmokeFailure("load_base_model", f"base model 로드 실패: {exc}", stdout_key="MODEL_LOAD_FAIL=1") from exc


def _build_lora_config(runtime: RuntimeBundle, adapter_path: Path) -> Any:
    cfg = _load_adapter_config(adapter_path)
    if not cfg:
        raise SmokeFailure("adapter_config", "adapter_config.json을 읽을 수 없습니다", stdout_key="MODEL_LOAD_FAIL=1")
    sig = inspect.signature(runtime.LoraConfig.__init__)
    allowed = set(sig.parameters.keys()) - {"self"}
    kwargs = {k: v for k, v in cfg.items() if k in allowed}
    return runtime.LoraConfig(**kwargs)


def _load_adapter_state(runtime: RuntimeBundle, adapter_path: Path) -> Dict[str, Any]:
    adapter_file = adapter_path / "adapter_model.safetensors"
    if not adapter_file.exists():
        raise SmokeFailure("adapter_weights", "adapter_model.safetensors 없음", exit_code=2, stdout_key="MODEL_LOAD_FAIL=1")
    try:
        sig = inspect.signature(runtime.load_safetensors)
        if "device" in sig.parameters:
            state = runtime.load_safetensors(str(adapter_file), device="cpu")
        else:
            state = runtime.load_safetensors(str(adapter_file))
    except Exception as exc:
        raise SmokeFailure("adapter_weights", f"safetensors 로드 실패: {exc}", stdout_key="MODEL_LOAD_FAIL=1") from exc

    casted: Dict[str, Any] = {}
    for k, v in state.items():
        try:
            if hasattr(v, "is_floating_point") and v.is_floating_point():
                casted[k] = v.to(dtype=runtime.torch.float32)
            else:
                casted[k] = v
        except Exception:
            casted[k] = v
    return casted


def _attach_adapter(runtime: RuntimeBundle, base_model: Any, adapter_path: Path, device: str) -> Tuple[Any, Dict[str, int]]:
    try:
        lora_config = _build_lora_config(runtime, adapter_path)
        model = runtime.get_peft_model(base_model, lora_config)
        state_dict = _load_adapter_state(runtime, adapter_path)
        load_result = model.load_state_dict(state_dict, strict=False)
        if hasattr(model, "to"):
            model = model.to(device)
        if hasattr(load_result, "missing_keys"):
            stats = {
                "missing_keys": len(getattr(load_result, "missing_keys", [])),
                "unexpected_keys": len(getattr(load_result, "unexpected_keys", [])),
            }
        elif isinstance(load_result, tuple) and len(load_result) == 2:
            stats = {"missing_keys": len(load_result[0]), "unexpected_keys": len(load_result[1])}
        else:
            stats = {"missing_keys": 0, "unexpected_keys": 0}
        return model, stats
    except SmokeFailure:
        raise
    except Exception as exc:
        raise SmokeFailure("attach_adapter", f"어댑터 attach 실패: {exc}", stdout_key="MODEL_LOAD_FAIL=1") from exc


def _set_eval_mode(model: Any) -> None:
    try:
        model.eval()
    except Exception as exc:
        raise SmokeFailure("eval_mode", f"model.eval 실패: {exc}", stdout_key="MODEL_LOAD_FAIL=1") from exc


def _apply_chat_template(tokenizer: Any, messages: List[Dict[str, str]], device: str) -> Tuple[Any, bool]:
    if not getattr(tokenizer, "chat_template", None):
        raise SmokeFailure("chat_template", "tokenizer.chat_template 없음", stdout_key="MODEL_LOAD_FAIL=1")
    kwargs = {
        "tokenize": True,
        "add_generation_prompt": True,
        "return_tensors": "pt",
    }
    supported = False
    try:
        model_inputs = tokenizer.apply_chat_template(messages, enable_thinking=False, **kwargs)
        supported = True
    except TypeError:
        model_inputs = tokenizer.apply_chat_template(messages, **kwargs)
    except Exception as exc:
        raise SmokeFailure("chat_template", f"apply_chat_template 실패: {exc}", stdout_key="MODEL_LOAD_FAIL=1") from exc
    return _move_inputs_to_device(model_inputs, device), supported


def _generate_text(runtime: RuntimeBundle, model: Any, tokenizer: Any, model_inputs: Any, max_new_tokens: int) -> str:
    kwargs: Dict[str, Any] = {
        "max_new_tokens": max_new_tokens,
        "do_sample": False,
        "use_cache": True,
    }
    if isinstance(model_inputs, dict):
        kwargs.update(model_inputs)
    elif hasattr(model_inputs, 'input_ids'):
        input_ids = model_inputs['input_ids']
        kwargs["input_ids"] = input_ids
    elif _is_tensor(model_inputs):
        kwargs["input_ids"] = model_inputs
    else:
        kwargs["input_ids"] = model_inputs
    with _no_grad(runtime.torch):
        try:
            outputs = model.generate(**kwargs)
        except Exception as exc:
            raise SmokeFailure("generate", f"generate 실패: {exc}", stdout_key="FORMAT_PLAIN_TEXT_FAIL=1") from exc
    new_ids = _extract_generated_ids(outputs, model_inputs)
    return _decode_text(tokenizer, new_ids)


# ---------------------------------------------------------------------------
# Main execution
# ---------------------------------------------------------------------------


def execute_output_format_smoke(
    adapter_path: Path,
    base_model_id_cli: Optional[str],
    device: str,
    output_dir: Path,
    seed: int,
    max_new_tokens: int,
    strict_json_only: bool,
) -> Tuple[int, Dict[str, Any], str]:
    recorder = Recorder()
    result: Dict[str, Any] = {
        "MODEL_LOAD_OK": 0,
        "model_load_dtype": "float32",
        "generation_config": {"max_new_tokens": max_new_tokens, "do_sample": False},
        "prompt_version": PROMPT_VERSION,
        "FORMAT_PLAIN_TEXT_OK": 0,
        "FORMAT_PLAIN_TEXT_FAIL": 0,
        "FORMAT_JSON_OK": 0,
        "FORMAT_JSON_FAIL": 0,
        "FORMAT_TOOL_CALL_OK": 0,
        "FORMAT_TOOL_CALL_FAIL": 0,
        "FORMAT_PLAIN_TEXT_OUTPUT": None,
        "FORMAT_JSON_OUTPUT": None,
        "FORMAT_JSON_PARSED": None,
        "FORMAT_TOOL_CALL_OUTPUT": None,
        "FORMAT_TOOL_CALL_PARSED": None,
        "json_parse_success": False,
        "json_required_keys_present": False,
        "json_extraction_mode": None,
        "tool_call_has_tool_name": False,
        "tool_call_has_arguments": False,
        "tool_call_arguments_is_dict": False,
        "tool_call_extraction_mode": None,
        "functional_ok": 0,
        "format_ok_count": 0,
        "OUTPUT_FORMAT_SMOKE_OK": 0,
        "OUTPUT_FORMAT_SMOKE_FAIL": 0,
        "failure_codes": [],
        "strict_json_only": bool(strict_json_only),
        "adapter_path": str(adapter_path),
        "adapter_digest_sha256_16": _sha256_16(adapter_path / "adapter_model.safetensors"),
        "resolved_base_model_id": resolve_base_model_id(adapter_path, base_model_id_cli),
        "device": device,
        "seed": seed,
        "runtime_backend": "unknown",
        "execution_mode": "unknown",
        "execution_mode_basis": {"runtime_backend": "unknown", "adapter_digest_match": False},
        "stdout_log_path": str(output_dir / STDOUT_FILENAME),
        "chat_template_enable_thinking_supported": None,
        "chat_template_enable_thinking_fallback_used": None,
        "adapter_load_mode": "direct_lora_safetensors",
        "adapter_state_missing_keys": None,
        "adapter_state_unexpected_keys": None,
        "adapter_state_missing_keys_expected": ADAPTER_MISSING_KEYS_EXPECTED,
        "adapter_state_unexpected_keys_expected": ADAPTER_UNEXPECTED_KEYS_EXPECTED,
        "ADAPTER_MISSING_KEYS_WARN": 0,
    }
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        runtime = _load_runtime_bundle()
        _set_seeds(seed, runtime.torch)
        if runtime.backend_name != "real" and result["adapter_digest_sha256_16"] is None:
            result["adapter_digest_sha256_16"] = hashlib.sha256(b"embedded_test_stub_adapter").hexdigest()[:16]
        result["runtime_backend"] = runtime.backend_name
        result["execution_mode"] = resolve_execution_mode(result["adapter_digest_sha256_16"], runtime.backend_name)
        result["execution_mode_basis"] = {
            "runtime_backend": runtime.backend_name,
            "adapter_digest_match": result["adapter_digest_sha256_16"] == REAL_ADAPTER_DIGEST,
        }
        if runtime.backend_name == "real":
            if result["adapter_digest_sha256_16"] is None:
                raise SmokeFailure("adapter_path", "adapter_model.safetensors 없음", exit_code=2, stdout_key="MODEL_LOAD_FAIL=1")
            if device == "cuda" and (not hasattr(runtime.torch, "cuda") or not runtime.torch.cuda.is_available()):
                raise SmokeFailure("device", "device=cuda 이지만 CUDA를 사용할 수 없습니다", exit_code=2, stdout_key="MODEL_LOAD_FAIL=1")
            if device not in {"cuda", "cpu"}:
                raise SmokeFailure("device", f"지원하지 않는 device: {device}", exit_code=2, stdout_key="MODEL_LOAD_FAIL=1")

        tokenizer = _load_tokenizer(runtime, adapter_path, result["resolved_base_model_id"])
        base_model = _load_base_model(runtime, result["resolved_base_model_id"])
        model, adapter_stats = _attach_adapter(runtime, base_model, adapter_path, device)
        _set_eval_mode(model)
        result["MODEL_LOAD_OK"] = 1
        result["adapter_state_missing_keys"] = adapter_stats["missing_keys"]
        result["adapter_state_unexpected_keys"] = adapter_stats["unexpected_keys"]
        result["ADAPTER_MISSING_KEYS_WARN"] = compute_adapter_missing_keys_warn(adapter_stats["missing_keys"])
        recorder.emit("MODEL_LOAD_OK=1")

        # common info from first template application
        _, support_plain = _apply_chat_template(tokenizer, PLAIN_TEXT_MESSAGES, device)
        result["chat_template_enable_thinking_supported"] = bool(support_plain)
        result["chat_template_enable_thinking_fallback_used"] = not bool(support_plain)
        chat_template_marker = "CHAT_TEMPLATE_ENABLE_THINKING_SUPPORTED=1" if support_plain else "CHAT_TEMPLATE_ENABLE_THINKING_FALLBACK=1"

        # Plain text
        plain_inputs, _ = _apply_chat_template(tokenizer, PLAIN_TEXT_MESSAGES, device)
        plain_text = _generate_text(runtime, model, tokenizer, plain_inputs, max_new_tokens)
        plain_check = validate_plain_text_output(plain_text)
        result["FORMAT_PLAIN_TEXT_OUTPUT"] = plain_text
        if plain_check["ok"]:
            result["FORMAT_PLAIN_TEXT_OK"] = 1
            recorder.emit("FORMAT_PLAIN_TEXT_OK=1")
        else:
            result["FORMAT_PLAIN_TEXT_FAIL"] = 1
            result["failure_codes"].extend(plain_check["failure_codes"])
            recorder.emit("FORMAT_PLAIN_TEXT_FAIL=1")

        # JSON
        json_inputs, _ = _apply_chat_template(tokenizer, JSON_MESSAGES, device)
        json_text = _generate_text(runtime, model, tokenizer, json_inputs, max_new_tokens)
        json_check = validate_json_output(json_text, strict_json_only=strict_json_only)
        result["FORMAT_JSON_OUTPUT"] = json_text
        result["FORMAT_JSON_PARSED"] = json_check["parsed"]
        result["json_parse_success"] = bool(json_check["json_parse_success"])
        result["json_required_keys_present"] = bool(json_check["json_required_keys_present"])
        result["json_extraction_mode"] = json_check["json_extraction_mode"]
        if json_check["ok"]:
            result["FORMAT_JSON_OK"] = 1
            recorder.emit("FORMAT_JSON_OK=1")
        else:
            result["FORMAT_JSON_FAIL"] = 1
            result["failure_codes"].extend(json_check["failure_codes"])
            recorder.emit("FORMAT_JSON_FAIL=1")

        # tool call
        tool_inputs, _ = _apply_chat_template(tokenizer, TOOL_CALL_MESSAGES, device)
        tool_text = _generate_text(runtime, model, tokenizer, tool_inputs, max_new_tokens)
        tool_check = validate_tool_call_output(tool_text, strict_json_only=strict_json_only)
        result["FORMAT_TOOL_CALL_OUTPUT"] = tool_text
        result["FORMAT_TOOL_CALL_PARSED"] = tool_check["parsed"]
        result["tool_call_has_tool_name"] = bool(tool_check["tool_call_has_tool_name"])
        result["tool_call_has_arguments"] = bool(tool_check["tool_call_has_arguments"])
        result["tool_call_arguments_is_dict"] = bool(tool_check["tool_call_arguments_is_dict"])
        result["tool_call_extraction_mode"] = tool_check["tool_call_extraction_mode"]
        if tool_check["ok"]:
            result["FORMAT_TOOL_CALL_OK"] = 1
            recorder.emit("FORMAT_TOOL_CALL_OK=1")
        else:
            result["FORMAT_TOOL_CALL_FAIL"] = 1
            result["failure_codes"].extend(tool_check["failure_codes"])
            recorder.emit("FORMAT_TOOL_CALL_FAIL=1")

        # final gate
        deduped_failure_codes: List[str] = []
        for code in result["failure_codes"]:
            if code not in deduped_failure_codes:
                deduped_failure_codes.append(code)
        result["failure_codes"] = deduped_failure_codes
        result["format_ok_count"] = int(result["FORMAT_PLAIN_TEXT_OK"]) + int(result["FORMAT_JSON_OK"]) + int(result["FORMAT_TOOL_CALL_OK"])
        result["functional_ok"] = 1 if result["format_ok_count"] == 3 else 0
        if result["functional_ok"] == 1:
            result["OUTPUT_FORMAT_SMOKE_OK"] = 1
            recorder.emit("OUTPUT_FORMAT_SMOKE_OK=1")
            exit_code = 0
        else:
            result["OUTPUT_FORMAT_SMOKE_FAIL"] = 1
            recorder.emit("OUTPUT_FORMAT_SMOKE_FAIL=1")
            exit_code = 1

        recorder.emit(chat_template_marker)
        recorder.emit(f"EXECUTION_MODE={result['execution_mode']}")
        if result["ADAPTER_MISSING_KEYS_WARN"] == 1:
            recorder.emit("ADAPTER_MISSING_KEYS_WARN=1")
    except SmokeFailure as exc:
        if exc.stdout_key:
            recorder.emit(exc.stdout_key)
        result["failure_stage"] = exc.stage
        result["failure_message"] = exc.message
        result["OUTPUT_FORMAT_SMOKE_FAIL"] = 1
        if exc.stage == "model_load":
            result["MODEL_LOAD_OK"] = 0
        recorder.emit("OUTPUT_FORMAT_SMOKE_FAIL=1")
        exit_code = exc.exit_code
    except Exception as exc:
        result["failure_stage"] = "unexpected"
        result["failure_message"] = str(exc)
        result["traceback"] = traceback.format_exc(limit=10)
        result["OUTPUT_FORMAT_SMOKE_FAIL"] = 1
        recorder.emit("OUTPUT_FORMAT_SMOKE_FAIL=1")
        exit_code = 1

    _json_dump(output_dir / RESULT_FILENAME, result)
    _write_text(output_dir / STDOUT_FILENAME, recorder.text())
    return exit_code, result, recorder.text()


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Butler AI output format smoke verification")
    ap.add_argument("--adapter-path", required=True, help="QLoRA adapter directory")
    ap.add_argument("--base-model-id", required=True, help="Local base model path or id")
    ap.add_argument("--device", default="cuda", choices=["cuda", "cpu"], help="cuda|cpu")
    ap.add_argument("--output-dir", required=True, help="Directory to save result files")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--max-new-tokens", type=int, default=128)
    ap.add_argument("--strict-json-only", default="true", choices=["true", "false"])
    return ap


def main(argv: Optional[List[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    strict_json_only = str(args.strict_json_only).lower() == "true"
    exit_code, _, _ = execute_output_format_smoke(
        adapter_path=Path(args.adapter_path),
        base_model_id_cli=args.base_model_id,
        device=args.device,
        output_dir=Path(args.output_dir),
        seed=args.seed,
        max_new_tokens=args.max_new_tokens,
        strict_json_only=strict_json_only,
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
