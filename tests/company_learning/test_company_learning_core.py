from __future__ import annotations

import json
import zipfile
from datetime import datetime, timezone

from butler_pc_core.company_learning import folder_ingest as ingest_module
from butler_pc_core.company_learning.folder_ingest import CompanyLearningIngestError, ingest_folder
from butler_pc_core.company_learning.handoff import create_company_learning_candidate
from butler_pc_core.company_learning.job_store import CompanyLearningJobStore
from butler_pc_core.company_learning.understanding import build_understanding
from butler_pc_core.connect_loop.learning_event_schema import validate_learning_event
from butler_pc_core.connect_loop.learning_event_store import LearningEventStore


def _write_text(path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def test_folder_ingest_allowlist_skips_before_get_chunker(tmp_path, monkeypatch):
    folder = tmp_path / "docs"
    folder.mkdir()
    _write_text(folder / "supported.txt", "회의록\n프로젝트 일정\n담당자 점검")
    _write_text(folder / "unsupported.xyz", "이 파일은 기본 청커로 흘러가면 안 됩니다.")

    calls: list[dict[str, object]] = []
    real_get_chunker = ingest_module.get_chunker

    def wrapped_get_chunker(*args, **kwargs):
        calls.append({"args": args, "kwargs": kwargs})
        return real_get_chunker(*args, **kwargs)

    monkeypatch.setattr(ingest_module, "get_chunker", wrapped_get_chunker)

    result = ingest_folder(str(folder))

    assert result.counters.processed_files == 1
    assert result.counters.skipped_unsupported == 1
    assert len(calls) == 1
    assert calls[0]["kwargs"] == {"file_type": "meeting_minutes"}


def test_ooxml_preflight_rejects_bad_signature_before_extractor(tmp_path):
    folder = tmp_path / "docs"
    folder.mkdir()
    (folder / "fake.docx").write_bytes(b"not-a-zip-document")

    try:
        ingest_folder(str(folder))
    except CompanyLearningIngestError as exc:
        assert exc.fail_class == "NO_INDEXABLE_FILES"
    else:  # pragma: no cover - defensive
        raise AssertionError("bad OOXML signature should not be indexed")


def test_ooxml_preflight_rejects_extreme_compression_ratio(tmp_path):
    folder = tmp_path / "docs"
    folder.mkdir()
    with zipfile.ZipFile(folder / "bomb.docx", "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", "0" * 1_000_000)

    try:
        ingest_folder(str(folder))
    except CompanyLearningIngestError as exc:
        assert exc.fail_class == "NO_INDEXABLE_FILES"
    else:  # pragma: no cover - defensive
        raise AssertionError("high compression ratio archive should not be indexed")


def test_extracted_char_limit_fails_closed_without_chunking(tmp_path, monkeypatch):
    folder = tmp_path / "docs"
    folder.mkdir()
    _write_text(folder / "too-large.txt", "0123456789abcdef")

    monkeypatch.setattr(
        ingest_module,
        "get_chunker",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("chunker must not run")),
    )

    try:
        ingest_folder(str(folder), max_extracted_chars_per_file=8)
    except CompanyLearningIngestError as exc:
        assert exc.fail_class == "NO_INDEXABLE_FILES"
    else:  # pragma: no cover - defensive
        raise AssertionError("over-limit extracted text should not be indexed")


def test_total_extracted_char_limit_skips_later_files(tmp_path):
    folder = tmp_path / "docs"
    folder.mkdir()
    _write_text(folder / "a.txt", "업무 정책 검토")
    _write_text(folder / "b.txt", "승인 절차 점검")

    result = ingest_folder(str(folder), max_extracted_chars_per_file=100, max_total_extracted_chars=10)

    assert result.counters.processed_files == 1
    assert result.counters.skipped_limit == 1


def test_chunk_source_id_is_digest_based_and_index_retrieves(tmp_path):
    folder = tmp_path / "docs"
    folder.mkdir()
    raw_name = "raw-client-folder-name.txt"
    _write_text(folder / raw_name, "회사 업무 정책과 검토 절차를 로컬에서 확인합니다.")

    result = ingest_folder(str(folder))

    assert result.chunks
    for chunk in result.chunks:
        assert chunk.source_file.startswith("file:")
        assert raw_name not in chunk.source_file
        assert "/" not in chunk.source_file
        assert "\\" not in chunk.source_file
        assert raw_name not in chunk.chunk_id

    retrieved = result.index.bm25.search("업무 정책", top_k=1)
    assert retrieved


def test_understanding_binds_every_claim_to_digest_only_evidence(tmp_path):
    folder = tmp_path / "docs"
    folder.mkdir()
    _write_text(folder / "policy.md", "정책 검토 절차와 승인 흐름을 관리합니다.")
    result = ingest_folder(str(folder))
    job = CompanyLearningJobStore().create_completed(result)

    understanding = build_understanding(job, llm_status="no_model")

    assert understanding["schema_version"] == "company_learning.understanding.v1"
    assert understanding["llm_status"] == "no_model"
    assert understanding["claims"]
    assert understanding["needs_review"] is False
    encoded = json.dumps(understanding, ensure_ascii=False)
    assert "policy.md" not in encoded
    assert "정책 검토 절차와 승인 흐름" not in encoded
    for claim in understanding["claims"]:
        assert claim["evidence_chips"]
        for chip in claim["evidence_chips"]:
            assert chip["chunk_digest"].startswith("sha256:")
            assert chip["source_id"].startswith("file:")
            assert "snippet" not in chip


def test_handoff_appends_schema_valid_candidate_without_training_flag(tmp_path):
    folder = tmp_path / "docs"
    folder.mkdir()
    _write_text(folder / "handoff.txt", "로컬 업무 자료를 후보 등록 전 검토합니다.")
    result = ingest_folder(str(folder))
    job = CompanyLearningJobStore().create_completed(result)
    store = LearningEventStore()

    handoff = create_company_learning_candidate(
        job,
        store=store,
        llm_status="not_used",
        now=datetime(2026, 6, 20, tzinfo=timezone.utc),
    )

    assert handoff.fail_class is None
    assert handoff.event is not None
    event = validate_learning_event(handoff.event)
    assert event["status"] == "CANDIDATE"
    assert event["verified_for_training"] is False
    assert event["schema_version"] == "learning_event.v1"
    assert event["label"] == {"intent_label": "memory_search", "target_box_id": "helper1", "quality": "fair"}
    assert event["policy_approval"]["reason_code"] == "FOLDER_UNDERSTANDING_CANDIDATE"
    assert event["approved_text_ref"].startswith("vault://company-learning/")
    assert "source_kind" not in event


def test_handoff_dlp_failure_blocks_append(tmp_path, monkeypatch):
    folder = tmp_path / "docs"
    folder.mkdir()
    _write_text(folder / "blocked.txt", "로컬 업무 자료를 후보 등록 전 검토합니다.")
    result = ingest_folder(str(folder))
    job = CompanyLearningJobStore().create_completed(result)
    store = LearningEventStore()

    from butler_pc_core.company_learning import handoff as handoff_module

    monkeypatch.setattr(
        handoff_module,
        "scan_runtime_text",
        lambda _text: {
            "passed": False,
            "pii_detected": True,
            "secret_detected": False,
            "policy_violation": False,
        },
    )

    handoff = create_company_learning_candidate(job, store=store)

    assert handoff.event is None
    assert handoff.fail_class == "HANDOFF_DLP_FAILED"
    assert store.events == {}
