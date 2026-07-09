from __future__ import annotations

import sys
from pathlib import Path

from butler_pc_core.cards.box3.helper_sdk_bridge import HelperSdkBridge


def test_env_file_sdk_import_registers_module_before_dataclass_exec(tmp_path: Path, monkeypatch) -> None:
    sdk_path = tmp_path / "helper7_table_figure_sdk.py"
    sdk_path.write_text(
        """
from dataclasses import dataclass


@dataclass(frozen=True)
class EvidenceRecord:
    text: str


def parse_for_evidence(reference_payload):
    record = EvidenceRecord(reference_payload[0])
    return [{
        "evidence_id": "env-file-h7-1",
        "text": record.text,
        "source_text": record.text,
        "kind": "text",
    }]
""",
        encoding="utf-8",
    )
    sys.modules.pop("helper7_table_figure_sdk", None)
    monkeypatch.setenv("BUTLER_HELPER7_TABLE_FIGURE_SDK_PATH", str(sdk_path))

    evidence = HelperSdkBridge().parse_evidence(["테스트 문서"])

    assert evidence.parse_success is True
    assert evidence.fail_class is None
    assert len(evidence.evidence_units_runtime) == 1
    assert "helper7_table_figure_sdk" in sys.modules
