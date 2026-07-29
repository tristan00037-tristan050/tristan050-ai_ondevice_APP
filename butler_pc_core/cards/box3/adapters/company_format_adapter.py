
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# 박스 3 real adapter 위치 정합(표준 156): ALG 원본의 `admin_policy/*` 경로 의존성을
# MAINDEV `company_policy/*` 단일 모듈 경로로 매핑한다. `DeviceLocalEncryptedFormatStore`
# 및 `FormatStoreError` 는 MAINDEV 의 `CompanyFormatStore` / `VaultError` 와 동치 역할.
from butler_pc_core.company_policy.contracts import CompanyFormat
from butler_pc_core.company_policy.contracts import sha256_text as sha256_digest_text
from butler_pc_core.company_policy.storage import CompanyFormatStore as DeviceLocalEncryptedFormatStore
from butler_pc_core.company_policy.vault import VaultError as FormatStoreError
from butler_pc_core.learning_capability.consumer_bindings import (
    default_consumer_binding_store,
)


@dataclass(frozen=True)
class CompanyFormatApplication:
    format_id: str | None
    format_applied: bool
    needs_review: bool
    formatted_digest: str | None
    format_digest: str | None
    template_digest: str | None
    fail_class: str | None
    external_send_zero: bool = True
    raw_saved_zero: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "helper3.company_format_application.v1",
            "format_id": self.format_id,
            "format_applied": self.format_applied,
            "needs_review": self.needs_review,
            "formatted_digest": self.formatted_digest,
            "format_digest": self.format_digest,
            "template_digest": self.template_digest,
            "fail_class": self.fail_class,
            "external_send_zero": self.external_send_zero,
            "raw_saved_zero": self.raw_saved_zero,
        }


def apply_company_format_runtime(
    *,
    draft_text_runtime_only: str,
    format_id: str | None,
    store: DeviceLocalEncryptedFormatStore,
) -> CompanyFormatApplication:
    if not format_id:
        return CompanyFormatApplication(format_id=None, format_applied=False, needs_review=True, formatted_digest=None, format_digest=None, template_digest=None, fail_class="FORMAT_ID_MISSING")
    company_format = store.get_format(format_id)
    if company_format is None or company_format.status != "ACTIVE":
        return CompanyFormatApplication(format_id=format_id, format_applied=False, needs_review=True, formatted_digest=None, format_digest=None, template_digest=None, fail_class="FORMAT_NOT_REGISTERED")
    try:
        template = store.load_template_runtime_only(company_format)
    except FormatStoreError as exc:
        return CompanyFormatApplication(format_id=format_id, format_applied=False, needs_review=True, formatted_digest=None, format_digest=company_format.format_digest, template_digest=company_format.template_digest, fail_class=str(exc))
    # Runtime-only formatting. Persisted result is a digest only; caller may use
    # the plaintext in process memory to render a response, but audit/evidence
    # receives only formatted_digest.
    formatted_runtime = template.replace("{draft}", draft_text_runtime_only) if "{draft}" in template else f"{template}\n\n{draft_text_runtime_only}"
    try:
        default_consumer_binding_store().record(
            "company_format",
            company_format.format_digest,
            "Box3.apply_company_format_runtime.v1",
        )
    except Exception:
        pass
    return CompanyFormatApplication(
        format_id=format_id,
        format_applied=True,
        needs_review=False,
        formatted_digest=sha256_digest_text(formatted_runtime),
        format_digest=company_format.format_digest,
        template_digest=company_format.template_digest,
        fail_class=None,
    )
