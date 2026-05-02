"""
Butler Fact Pack v1

검증된 한국 사실 Q&A 모듈. LLM의 한국 사실 지식 부족을 보완.

공개 인터페이스:
    FactPack         — 메인 클래스
    Fact             — 단일 사실 항목
    FactMatch        — 매칭 결과
    FactPackAuditEntry — 감사 로그 항목
"""

from .pack import FactPack
from .schema import Fact, FactMatch, FactPackAuditEntry, FactPackFile

__all__ = ["FactPack", "Fact", "FactMatch", "FactPackFile", "FactPackAuditEntry"]
__version__ = "1.0.0"
