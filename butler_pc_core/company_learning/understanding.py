from __future__ import annotations

from collections import Counter
from typing import Any

from butler_pc_core.company_policy.contracts import sha256_text, stable_json_digest
from butler_pc_core.retrieval.chunkers import Chunk
from butler_pc_core.retrieval.pipeline import HybridRetrievalPipeline

from .job_store import CompanyLearningJob

_TYPE_LABELS = {
    ".txt": "text",
    ".md": "markdown",
    ".pdf": "pdf",
    ".docx": "word",
    ".doc": "word_legacy",
    ".xlsx": "spreadsheet",
    ".xls": "spreadsheet_legacy",
    ".csv": "csv",
    ".pptx": "presentation",
    ".ppt": "presentation_legacy",
    ".eml": "email",
    ".msg": "email_legacy",
}


def _chip_for(chunk: Chunk) -> dict[str, Any]:
    return {
        "schema_version": "company_learning.file_evidence_chip.v1",
        "chunk_digest": sha256_text(chunk.text),
        "source_id": chunk.source_file,
        "page_or_sheet": chunk.page_or_sheet,
        "section_digest": stable_json_digest(
            {
                "source_id": chunk.source_file,
                "section_title": chunk.section_title or "",
            }
        ),
        "char_span": [
            int(chunk.start_char or 0),
            int(chunk.end_char or max(len(chunk.text), 1)),
        ],
    }


def _doc_type_distribution(counters: dict[str, Any]) -> list[dict[str, Any]]:
    by_extension = counters.get("by_extension")
    if not isinstance(by_extension, dict):
        return []
    dist = []
    for ext, count in sorted(by_extension.items()):
        dist.append(
            {
                "type": _TYPE_LABELS.get(str(ext), "other_allowed"),
                "extension_digest": sha256_text(str(ext)),
                "count": int(count),
            }
        )
    return dist


def _safe_topics(distribution: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "topic": f"{row['type']}_materials",
            "evidence_count": int(row["count"]),
        }
        for row in distribution
        if int(row.get("count", 0)) > 0
    ][:8]


def _retrieved_evidence(job: CompanyLearningJob) -> list[dict[str, Any]]:
    pipeline = HybridRetrievalPipeline(job.index)
    results = pipeline.retrieve("업무 정책 규정 절차 양식 회계 고객 프로젝트", top_k=5)
    source: list[Chunk] = [result.chunk for result in results]
    if not source:
        source = job.chunks[:5]
    seen: set[str] = set()
    chips: list[dict[str, Any]] = []
    for chunk in source:
        chip = _chip_for(chunk)
        key = chip["chunk_digest"]
        if key in seen:
            continue
        seen.add(key)
        chips.append(chip)
    return chips


def build_understanding(job: CompanyLearningJob, *, llm_status: str = "not_used") -> dict[str, Any]:
    with job.lock:
        if job.understanding is not None:
            return dict(job.understanding)

        counters = dict(job.counters)
        distribution = _doc_type_distribution(counters)
        topics = _safe_topics(distribution)
        chips = _retrieved_evidence(job)
        evidence_chip_count = len(chips)
        processed_files = int(counters.get("processed_files", 0) or 0)
        chunk_count = int(counters.get("chunk_count", 0) or 0)

        claims: list[dict[str, Any]] = []
        if evidence_chip_count > 0:
            claims.append(
                {
                    "claim_id": "claim-local-index-ready",
                    "claim_runtime_text": f"지원 확장자 문서 {processed_files}개가 이 기기 안에서 인덱싱되었습니다.",
                    "evidence_chips": chips[:2],
                }
            )
            if distribution:
                type_names = ", ".join(row["type"] for row in distribution[:4])
                claims.append(
                    {
                        "claim_id": "claim-doc-type-distribution",
                        "claim_runtime_text": f"확인된 자료 유형은 {type_names} 범주입니다.",
                        "evidence_chips": chips[:2],
                    }
                )
            claims.append(
                {
                    "claim_id": "claim-handoff-candidate-ready",
                    "claim_runtime_text": "근거 칩이 연결된 업무 파악 결과가 학습 후보 등록 전 검토 자료로 준비되었습니다.",
                    "evidence_chips": chips[:3],
                }
            )

        needs_review = evidence_chip_count == 0 or processed_files == 0 or chunk_count == 0
        summary = (
            f"로컬 인덱싱 결과: 지원 파일 {processed_files}개, 청크 {chunk_count}개, "
            f"근거 칩 {evidence_chip_count}개를 확인했습니다. "
            "학습 실행이 아니라 관리자 검토용 후보 등록 단계입니다."
        )
        if needs_review:
            summary += " 근거가 부족해 관리자 확인이 필요합니다."

        understanding = {
            "schema_version": "company_learning.understanding.v1",
            "job_id": job.job_id,
            "folder_digest": job.folder_digest,
            "ingest_digest": job.ingest_digest,
            "integration_mode": "local_only",
            "llm_status": llm_status if llm_status in {"ready", "no_model", "error", "not_used"} else "error",
            "doc_type_distribution": distribution,
            "topics": topics,
            "claims": claims,
            "summary_runtime_text": summary,
            "needs_review": needs_review,
            "needs_review_reason": "INSUFFICIENT_EVIDENCE" if needs_review else None,
            "evidence_chip_count": evidence_chip_count,
            "raw_text_logged": False,
            "external_send_zero": True,
        }
        job.understanding = dict(understanding)
        return understanding
