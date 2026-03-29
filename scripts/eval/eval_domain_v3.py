from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from scripts.eval.eval_basic_v3 import generate_eval_response
from scripts.eval.eval_judge_rule_v1 import judge


DOMAIN_THRESHOLDS = {
    "legal": 0.60,
    "finance": 0.60,
    "medical": 0.60,
    "admin": 0.55,
    "general": 0.50,
}

REGULATED_DOMAINS = {"legal", "finance", "medical"}


def _scenario(case_id: str, prompt: str, keywords: List[str]):
    return {
        "case_id": case_id,
        "prompt": prompt,
        "keywords": keywords,
    }


DOMAIN_EVAL_SETS: Dict[str, List[dict]] = {
    "legal": [
        _scenario("legal-01", "근로계약서 필수 항목은?", ["임금", "근로시간", "휴일", "업무"]),
        _scenario("legal-02", "해고 예고 기본 기준은?", ["30일"]),
        _scenario("legal-03", "연차유급휴가 발생 기준은?", ["1년", "15일", "80%"]),
        _scenario("legal-04", "퇴직금 지급 판단 요소는?", ["1년", "계속근로"]),
        _scenario("legal-05", "최저임금 위반 시 제재는?", ["과태료", "징역"]),
        _scenario("legal-06", "육아휴직 기본 기간은?", ["1년"]),
        _scenario("legal-07", "산업재해 보상 신청 기관은?", ["근로복지공단"]),
        _scenario("legal-08", "직장 내 괴롭힘 처리 절차는?", ["신고", "조사", "조치"]),
        _scenario("legal-09", "임금 체불 신고 경로는?", ["고용노동부", "진정"]),
        _scenario("legal-10", "계약 검토 체크리스트 핵심은?", ["당사자", "의무", "기한", "위약"]),
    ],
    "finance": [
        _scenario("finance-01", "법인세 신고 기한은?", ["3개월"]),
        _scenario("finance-02", "부가가치세 일반과세자 신고 주기는?", ["6개월", "예정신고"]),
        _scenario("finance-03", "원천징수 대상 소득은?", ["근로소득", "사업소득", "이자", "배당"]),
        _scenario("finance-04", "종합소득세 신고 기간은?", ["5월"]),
        _scenario("finance-05", "세금계산서 발급 의무자는?", ["사업자"]),
        _scenario("finance-06", "양도소득세 신고 기한은?", ["2개월"]),
        _scenario("finance-07", "증여세 신고 기한은?", ["3개월"]),
        _scenario("finance-08", "상속세 신고 기한은?", ["6개월"]),
        _scenario("finance-09", "가산세 종류 예시는?", ["무신고", "과소신고", "납부지연"]),
        _scenario("finance-10", "재무 보고 검토 포인트는?", ["정확", "증빙", "일관", "기한"]),
    ],
    "medical": [
        _scenario("medical-01", "건강보험 피부양자 등록 요건은?", ["소득", "재산", "부양"]),
        _scenario("medical-02", "건강검진 대상자 기준은?", ["2년", "짝수", "홀수"]),
        _scenario("medical-03", "산재보험 적용 대상은?", ["근로자"]),
        _scenario("medical-04", "요양급여 본인부담률 예시는?", ["20%", "30%"]),
        _scenario("medical-05", "의료급여 1종과 2종 차이는?", ["1종", "2종", "본인부담"]),
        _scenario("medical-06", "장기요양보험 등급 기준은?", ["1등급", "5등급"]),
        _scenario("medical-07", "실손보험 청구 서류 예시는?", ["영수증", "진단서"]),
        _scenario("medical-08", "건강보험료 산정 기준은?", ["소득", "재산"]),
        _scenario("medical-09", "처방전 유효기간 예시는?", ["3일", "7일"]),
        _scenario("medical-10", "의료 안내문 검토 핵심은?", ["정확", "주의", "대상", "절차"]),
    ],
    "admin": [
        _scenario("admin-01", "민원 처리 기간 예시는?", ["7일", "10일"]),
        _scenario("admin-02", "행정심판 청구 기간은?", ["90일"]),
        _scenario("admin-03", "정보공개 청구 처리 기간은?", ["10일"]),
        _scenario("admin-04", "행정소송 제소 기간 예시는?", ["1년", "6개월"]),
        _scenario("admin-05", "입찰 공고 체크리스트는?", ["자격", "일정", "규격", "평가"]),
        _scenario("admin-06", "행정 안내문 품질 기준은?", ["명확", "기한", "대상", "절차"]),
        _scenario("admin-07", "정보공개 요청 처리 기본은?", ["접수", "검토", "제공", "비공개"]),
        _scenario("admin-08", "권한 신청서 검토 포인트는?", ["신청자", "권한", "사유", "승인"]),
        _scenario("admin-09", "인수인계 문서 핵심은?", ["현황", "일정", "리스크", "연락처"]),
        _scenario("admin-10", "공지사항 검토 항목은?", ["대상", "시행일", "문의", "예외"]),
    ],
    "general": [
        _scenario("general-01", "버틀러의 기본 역할은?", ["AI", "어시스턴트", "온디바이스"]),
        _scenario("general-02", "버틀러 데이터 보안 원칙은?", ["외부", "전송", "없음", "내부"]),
        _scenario("general-03", "업무 자동화 설계의 출발점은?", ["목표", "반복", "우선순위"]),
        _scenario("general-04", "좋은 AI 응답의 조건은?", ["정확", "근거", "명확"]),
        _scenario("general-05", "온디바이스 AI 장점은?", ["지연", "보안", "오프라인"]),
        _scenario("general-06", "프로젝트 회고 핵심은?", ["목표", "결과", "문제", "개선"]),
        _scenario("general-07", "지식베이스 문서화 원칙은?", ["버전", "출처", "일관성", "검색"]),
        _scenario("general-08", "팀 생산성 향상 방법은?", ["자동화", "표준화", "우선순위"]),
        _scenario("general-09", "품질 게이트의 역할은?", ["회귀", "차단", "기준", "배포"]),
        _scenario("general-10", "실험 결과 기록 항목은?", ["설정", "지표", "결과", "재현"]),
    ],
}


@dataclass
class DomainEvalResult:
    scores: Dict[str, float] = field(default_factory=dict)
    passed: Dict[str, bool] = field(default_factory=dict)
    fail_reasons: List[str] = field(default_factory=list)
    all_passed: bool = False
    scenario_results: Dict[str, List[dict]] = field(default_factory=dict)
    sample_counts: Dict[str, int] = field(default_factory=dict)
    judge_extension: dict = field(default_factory=lambda: {
        "llm_as_judge": {"enabled": False, "calibrated": False, "notes": None},
        "human_spot_check": {"enabled": False, "sample_size": 0, "notes": None},
        "rule_judge": {"enabled": True, "source": "rule_v1", "weight": 0.30},
    })


def _keyword_score(response: str, keywords: List[str]) -> float:
    if not keywords:
        return 1.0
    lowered = response.lower()
    return sum(1 for keyword in keywords if keyword.lower() in lowered) / len(keywords)


def _scenario_score(response: str, scenario: dict, domain: str) -> tuple[float, dict]:
    keyword_score = _keyword_score(response, scenario.get("keywords", []))
    judge_result = judge(response, domain, sub_category=None, threshold=0.40)
    final_score = (0.70 * keyword_score) + (0.30 * judge_result.score)
    row = {
        "case_id": scenario.get("case_id"),
        "prompt": scenario.get("prompt"),
        "response": response,
        "keyword_score": round(keyword_score, 4),
        "judge_score": judge_result.score,
        "judge_source": judge_result.source,
        "judge_confidence": judge_result.confidence,
        "judge_passed": judge_result.passed,
        "judge_details": judge_result.details,
        "final_score": round(final_score, 4),
    }
    return final_score, row


def run_domain_eval(model, tokenizer, dry_run: bool = False) -> DomainEvalResult:
    result = DomainEvalResult()
    if dry_run:
        for domain, scenarios in DOMAIN_EVAL_SETS.items():
            result.scores[domain] = 0.99
            result.passed[domain] = True
            result.sample_counts[domain] = len(scenarios)
            result.scenario_results[domain] = [
                {
                    "case_id": scenario["case_id"],
                    "prompt": scenario["prompt"],
                    "response": "dry-run deterministic answer",
                    "keyword_score": 0.99,
                    "judge_score": 0.98,
                    "judge_source": "rule_v1",
                    "judge_confidence": 0.95,
                    "judge_passed": True,
                    "judge_details": {"dry_run": True, "threshold": 0.40},
                    "final_score": 0.987,
                }
                for scenario in scenarios
            ]
        result.all_passed = True
        return result

    for domain, scenarios in DOMAIN_EVAL_SETS.items():
        rows: List[dict] = []
        scenario_scores: List[float] = []
        for scenario in scenarios:
            response = generate_eval_response(model, tokenizer, scenario["prompt"], max_new_tokens=256)
            score, row = _scenario_score(response, scenario, domain)
            rows.append(row)
            scenario_scores.append(score)

        score = sum(scenario_scores) / max(len(scenario_scores), 1)
        threshold = DOMAIN_THRESHOLDS[domain]
        result.scores[domain] = round(score, 4)
        result.passed[domain] = score >= threshold
        result.sample_counts[domain] = len(scenarios)
        result.scenario_results[domain] = rows

        if score < threshold:
            fail_code = f"EVAL_FAIL_DOMAIN_{domain.upper()}"
            result.fail_reasons.append(f"{fail_code}:{score:.3f}<{threshold:.2f}")

    result.all_passed = len(result.fail_reasons) == 0
    return result
