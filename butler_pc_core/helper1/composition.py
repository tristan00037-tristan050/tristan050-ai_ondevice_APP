"""Helper1 production composition root, invoked during Sidecar startup.

The source tree deliberately contains no path/env fallback. A signed native
extension must provide a fully assembled pipeline and a native execution
authority. Without that trust input the existing HTTP route remains present
and typed, but unavailable.
"""
from __future__ import annotations

import importlib
import importlib.machinery
from dataclasses import dataclass
from types import ModuleType

from .execution import NativeExecutionAuthority
from .approval_closure import ClosureVerdict
from .pipeline import Helper1AnswerPipeline
from .retrieval_policy import RetrievalPolicyAuthority
from .service import Helper1Service, get_helper1_service


class CompositionError(RuntimeError):
    pass


@dataclass(frozen=True)
class NativeProductAssembly:
    workspace_id: str
    session_digest: str
    pipeline: Helper1AnswerPipeline
    execution_authority: NativeExecutionAuthority
    retrieval_policy_authority: RetrievalPolicyAuthority
    closure_verdict: ClosureVerdict


def _native_module() -> ModuleType | None:
    try:
        module = importlib.import_module("_butler_helper1_native")
    except ModuleNotFoundError as exc:
        if exc.name == "_butler_helper1_native":
            return None
        raise CompositionError("HELPER1_NATIVE_IMPORT_FAILED") from exc
    origin = getattr(getattr(module, "__spec__", None), "origin", None)
    if not isinstance(origin, str) or not origin.endswith(tuple(importlib.machinery.EXTENSION_SUFFIXES)):
        raise CompositionError("HELPER1_NATIVE_EXTENSION_REQUIRED")
    return module


def load_native_product_assembly() -> NativeProductAssembly | None:
    """Load the signed native assembly without installing a parallel composition."""
    module = _native_module()
    if module is None:
        return None
    factory = getattr(module, "assemble_helper1_v2", None)
    if not callable(factory):
        raise CompositionError("HELPER1_NATIVE_FACTORY_MISSING")
    assembly = factory()
    if type(assembly) is not NativeProductAssembly:
        raise CompositionError("HELPER1_NATIVE_ASSEMBLY_INVALID")
    return assembly


def load_native_ablation_assembly(
    normal_index_manifest_sha256: str,
) -> NativeProductAssembly | None:
    """Load the protected canary-removed index through the native trust root."""
    module = _native_module()
    if module is None:
        return None
    factory = getattr(module, "assemble_helper1_v2_ablation", None)
    if not callable(factory):
        raise CompositionError("HELPER1_NATIVE_ABLATION_FACTORY_MISSING")
    assembly = factory(normal_index_manifest_sha256)
    if type(assembly) is not NativeProductAssembly:
        raise CompositionError("HELPER1_NATIVE_ABLATION_ASSEMBLY_INVALID")
    if assembly.pipeline.index.manifest.digest == normal_index_manifest_sha256:
        raise CompositionError("HELPER1_NATIVE_ABLATION_INDEX_INVALID")
    return assembly


def initialize_helper1_product(service: Helper1Service | None = None) -> bool:
    """Install the one native assembly, or preserve fail-closed unavailability."""
    target = service or get_helper1_service()
    assembly = load_native_product_assembly()
    if assembly is None:
        return False
    target.register_native_pipeline(
        assembly.workspace_id,
        assembly.pipeline,
        execution_authority=assembly.execution_authority,
        session_digest=assembly.session_digest,
        retrieval_policy_authority=assembly.retrieval_policy_authority,
        closure_verdict=assembly.closure_verdict,
    )
    return True
