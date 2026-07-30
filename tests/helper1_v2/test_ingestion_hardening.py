from __future__ import annotations

import io
import os
import uuid
import warnings
import zipfile

import pytest

from butler_pc_core.helper1.ingestion import (
    ApprovedFolderIngestor,
    HeadingChunker,
    IngestionError,
    ParsedDocument,
    parse_in_sandbox,
)


def _office_archive(names: tuple[str, ...]) -> bytes:
    value = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(value, "w") as archive:
            for name in names:
                archive.writestr(name, "<Types/>")
    return value.getvalue()


def test_extension_magic_mismatch_is_rejected_before_parser():
    with pytest.raises(IngestionError, match="DOCUMENT_MAGIC_MISMATCH"):
        parse_in_sandbox(b"not a PDF", ".pdf")
    with pytest.raises(IngestionError, match="DOCUMENT_MAGIC_MISMATCH"):
        parse_in_sandbox(b"not an OOXML package", ".docx")
    with pytest.raises(IngestionError, match="DOCUMENT_MAGIC_MISMATCH"):
        parse_in_sandbox(b"text\x00binary", ".txt")


def test_archive_duplicate_and_unicode_collision_are_rejected():
    duplicate = _office_archive(("[Content_Types].xml", "[Content_Types].xml"))
    with pytest.raises(
        IngestionError, match="DOCUMENT_ARCHIVE_NAME_COLLISION"
    ):
        parse_in_sandbox(duplicate, ".docx")

    collision = _office_archive(("word/Ａ.xml", "word/A.xml"))
    with pytest.raises(
        IngestionError, match="DOCUMENT_ARCHIVE_NAME_COLLISION"
    ):
        parse_in_sandbox(collision, ".docx")


def test_hidden_temporary_files_are_not_collected(tmp_path):
    (tmp_path / "approved.txt").write_text("승인된 문서", encoding="utf-8")
    (tmp_path / ".hidden.txt").write_text("숨김 문서", encoding="utf-8")
    (tmp_path / "~$lock.txt").write_text("잠금 파일", encoding="utf-8")
    descriptor = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        ingestor = ApprovedFolderIngestor(
            workspace_id=str(uuid.uuid4()),
            folder_fd=descriptor,
            workspace_key=b"k" * 32,
        )
        documents = ingestor.read_documents()
    finally:
        os.close(descriptor)
    assert len(documents) == 1
    assert documents[0].text == "승인된 문서"


def test_chunker_policy_binds_normalization_and_normalizes_content():
    chunker = HeadingChunker(max_chars=512, overlap_chars=32)
    document = ParsedDocument(
        source_id="src:one",
        document_revision_sha256="a" * 64,
        text="ＡＢＣ\r\n회사 규정",
        media_type="txt",
    )
    chunks = chunker.chunk(
        (document,),
        str(uuid.uuid4()),
        b"k" * 32,
    )
    assert chunks[0].text == "ABC\n회사 규정"
    assert len(chunker.policy_sha256) == 64
