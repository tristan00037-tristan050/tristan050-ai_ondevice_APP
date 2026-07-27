from __future__ import annotations

import sys
import importlib.util
from pathlib import Path

from butler_pc_core.cards.box3.helper_sdk_bridge import HelperSdkBridge


def test_explicit_sdk_import_registers_module_before_dataclass_exec(tmp_path: Path) -> None:
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
    spec = importlib.util.spec_from_file_location("helper7_table_figure_sdk", sdk_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["helper7_table_figure_sdk"] = module
    spec.loader.exec_module(module)

    evidence = HelperSdkBridge(helper7=module).parse_evidence(["테스트 문서"])

    assert evidence.parse_success is True
    assert evidence.fail_class is None
    assert len(evidence.evidence_units_runtime) == 1
    assert "helper7_table_figure_sdk" in sys.modules
