from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from butler_pc_core.app_data import product_data_root
from butler_pc_core.learning_capability.authorities import (
    CompanyFactAuthority,
    CompanyFormatAuthority,
    CompanyPolicyAuthority,
    FolderLearningAuthority,
)
from butler_pc_core.learning_capability.consumer_bindings import (
    default_consumer_binding_store,
)
from butler_pc_core.learning_capability.contracts import LearningCapabilityError
from butler_pc_core.learning_capability.generation_store import (
    DurableGenerationStore,
)
from butler_pc_core.learning_capability.service import LearningCapabilityService


router = APIRouter()
_SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
}


def get_learning_capability_service() -> LearningCapabilityService:
    # Lazy imports bind to the exact store singletons used by the product
    # mutation routes, not to a parallel inventory or UI-owned cache.
    from butler_pc_core.company_fact.routes import get_company_fact_store
    from butler_pc_core.sidecar.routes.admin_policy_format import (
        _FORMAT_STORE,
        _POLICY_STORE,
    )
    from butler_pc_core.sidecar.routes.company_learning import (
        _LEARNING_EVENT_STORE,
    )

    bindings = default_consumer_binding_store()
    generation_store = DurableGenerationStore(
        product_data_root(
            "learning-capability",
            legacy_name=".butler_learning_capability",
        )
        / "generation.json"
    )
    return LearningCapabilityService(
        authorities=(
            CompanyPolicyAuthority(_POLICY_STORE, bindings),
            CompanyFactAuthority(get_company_fact_store(), bindings),
            CompanyFormatAuthority(_FORMAT_STORE, bindings),
            FolderLearningAuthority(_LEARNING_EVENT_STORE, bindings),
        ),
        generation_store=generation_store,
    )


@router.get("/api/capabilities/learning")
def learning_capability_snapshot(
    service: LearningCapabilityService = Depends(
        get_learning_capability_service
    ),
) -> JSONResponse:
    try:
        payload = service.snapshot().to_dict()
        return JSONResponse(
            status_code=200,
            content=payload,
            headers=_SECURITY_HEADERS,
        )
    except LearningCapabilityError as exc:
        return JSONResponse(
            status_code=503,
            content=exc.to_dict(),
            headers=_SECURITY_HEADERS,
        )
    except Exception:
        return JSONResponse(
            status_code=503,
            content=LearningCapabilityError("INTERNAL_ERROR").to_dict(),
            headers=_SECURITY_HEADERS,
        )

