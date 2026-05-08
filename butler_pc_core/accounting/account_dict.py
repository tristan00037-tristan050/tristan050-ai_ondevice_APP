"""중소기업회계기준 표준 계정과목 사전 — 32개 계정과목별 정규식 패턴."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass(frozen=True)
class Account:
    code: str
    name: str
    keywords: List[str]        # re.search() 패턴 목록 (OR 결합)
    vendor_patterns: List[str] = field(default_factory=list)  # 거래처명 정규식
    sign: str = "+"            # "+" 수익/자산 증가, "-" 비용/부채 증가
    section: str = "other"     # 재무제표 섹션 분류


# 재무제표 섹션 정렬 순서
SECTION_ORDER: dict[str, int] = {
    "I_revenue": 0,
    "II_cogs": 1,
    "IV_sga": 2,
    "VI_non_op_revenue": 3,
    "VII_non_op_expense": 4,
    "other": 5,
}


# 패턴 우선순위: 목록 순서대로 매칭, 첫 번째 명중 계정 반환 (결정적)
ACCOUNTS: List[Account] = [
    # ── 수익 ────────────────────────────────────────────────────────────────
    Account("4010", "매출",
            [r"매출", r"판매수입", r"용역수입", r"서비스수입", r"수입금액", r"수입금"],
            [], sign="+", section="I_revenue"),
    Account("5010", "상품매출원가",
            [r"상품매입", r"물품구매", r"원재료구입", r"자재구매", r"부품구입",
             r"재고구매", r"매입", r"맑은유통", r"블리스대디"],
            [r"맑은유통", r"블리스대디"], sign="-", section="II_cogs"),
    Account("5020", "매출총이익",
            [r"매출총이익", r"재고조정", r"매출조정"],
            [], sign="+", section="II_cogs"),

    # ── 판매비와 관리비 (인건비) ─────────────────────────────────────────────
    Account("8010", "임원급여",
            [r"임원급여", r"대표이사급여", r"임원보수", r"이사급여"],
            [], sign="-", section="IV_sga"),
    Account("8020", "직원급여",
            [r"급여", r"임금", r"월급", r"봉급", r"인건비지급", r"급여이체",
             r"미지급.*급여", r"\d+월급여"],
            [], sign="-", section="IV_sga"),
    Account("8030", "상여금",
            [r"상여금", r"인센티브", r"성과급", r"특별상여"],
            [], sign="-", section="IV_sga"),
    Account("8040", "퇴직급여",
            [r"퇴직급여", r"퇴직금", r"퇴직위로금", r"퇴직충당금"],
            [], sign="-", section="IV_sga"),

    # ── 판매비와 관리비 (경비) ───────────────────────────────────────────────
    Account("8050", "복리후생비",
            [r"복리후생", r"식대보조", r"중식비", r"석식비", r"회식비",
             r"건강검진비", r"경조금", r"명절선물", r"생일선물", r"단체보험",
             r"휴가비", r"동호회비"],
            [], sign="-", section="IV_sga"),
    Account("8060", "여비교통비",
            [r"여비교통", r"출장비", r"항공료", r"철도요금", r"택시비",
             r"버스요금", r"고속도로.*통행료", r"주차료"],
            [r"코레일", r"한국철도", r"카카오T", r"카카오택시"], sign="-", section="IV_sga"),
    Account("8070", "접대비",
            [r"접대비", r"거래처.*식사", r"거래처.*선물", r"골프.*비용",
             r"접대.*비용", r"기업업무추진비"],
            [], sign="-", section="IV_sga"),
    Account("8080", "통신비",
            [r"통신비", r"이동통신요금", r"인터넷요금", r"전화요금",
             r"휴대폰요금", r"통신요금"],
            [r"KT", r"케이티", r"SKT", r"SK텔레콤", r"LGU\+", r"LG유플러스",
             r"SK브로드밴드", r"미래네트웍스"], sign="-", section="IV_sga"),
    Account("8090", "전력비",
            [r"수도요금", r"전기요금", r"도시가스요금", r"가스요금",
             r"전력요금", r"열요금", r"상하수도", r"예금결산이자",
             r"동건에너지"],
            [r"한국전력", r"한전", r"도시가스", r"서울도시가스", r"코원에너지",
             r"동건에너지", r"수원시상하수도"], sign="-", section="IV_sga"),
    Account("8100", "세금과공과금",
            [r"부가가치세", r"법인세납부", r"소득세납부", r"재산세",
             r"취득세", r"지방세납부", r"주민세", r"과태료",
             r"근로소득세", r"사업소득세", r"지방소득세", r"인지세",
             r"법원행정처"],
            [r"국세청", r"세무서", r"법원행정처", r"서울시", r"경기도",
             r"지방자치단체"], sign="-", section="IV_sga"),
    Account("8110", "감가상각비",
            [r"감가상각", r"상각비"],
            [], sign="-", section="IV_sga"),
    Account("8120", "지급임차료",
            [r"임차료", r"임대료납부", r"사무실임대", r"월세납부",
             r"공간임차", r"사무실임대료", r"매장임대료", r"렌탈료",
             r"롯데렌탈", r"스파크플러스"],
            [r"롯데렌탈"], sign="-", section="IV_sga"),
    Account("8130", "보험료",
            [r"보험료납부", r"보험료", r"화재보험", r"자동차보험", r"배상책임보험",
             r"산재보험료", r"고용보험료", r"건강보험", r"국민연금보험료"],
            [r"삼성화재", r"현대해상", r"DB손해보험", r"KB손해보험",
             r"메리츠화재", r"흥국화재", r"동부화재", r"마이퍼피"], sign="-", section="IV_sga"),
    Account("8140", "차량유지비",
            [r"주유비", r"경유구매", r"휘발유구매", r"엔진오일교환",
             r"차량수리비", r"타이어교체", r"세차비", r"차량유지",
             r"주유", r"정기주차비", r"주차비",
             r"케이엠파킹", r"케이엠파크", r"한미석유", r"광장오토모티브", r"충남카케어"],
            [r"SK에너지", r"GS칼텍스", r"현대오일뱅크", r"S-OIL",
             r"알뜰주유소", r"케이엠파킹", r"케이엠파크", r"한미석유",
             r"타임셀프주유소", r"남강주유소", r"광장오토모티브",
             r"충남카케어", r"클린파킹"], sign="-", section="IV_sga"),
    Account("8150", "경상연구개발비",
            [r"연구개발비", r"R&D비용", r"시험인증비", r"특허비용",
             r"기술개발비", r"연구비"],
            [r"백경특허", r"특허법인"], sign="-", section="IV_sga"),
    Account("8160", "운반비",
            [r"운반비", r"택배비", r"배송비", r"화물운송", r"물류비"],
            [], sign="-", section="IV_sga"),
    Account("8170", "교육훈련비",
            [r"교육비", r"연수비", r"세미나참가비", r"워크숍비용",
             r"자격증취득비", r"강의료", r"훈련비"],
            [], sign="-", section="IV_sga"),
    Account("8180", "도서인쇄비",
            [r"도서구입", r"서적구매", r"인쇄비", r"복사비",
             r"출판비", r"문서출력비"],
            [], sign="-", section="IV_sga"),
    Account("8190", "사무용품비",
            [r"사무용품", r"문구류구입", r"사무기기소모품", r"복사지구매",
             r"사무용품비"],
            [], sign="-", section="IV_sga"),
    Account("8200", "소모품비",
            [r"소모품구입", r"소모품비", r"토너구입", r"잉크구매",
             r"청소용품", r"위생용품", r"쿠팡"],
            [r"쿠팡"], sign="-", section="IV_sga"),
    Account("8210", "지급수수료",
            [r"수수료지급", r"컨설팅", r"자문료", r"대행수수료",
             r"법무비용", r"세무자문비", r"노무자문비", r"변호사비용",
             r"플랫폼수수료", r"중개수수료",
             r"Amazon.*AWS", r"OPENAI", r"ChatGPT",
             r"지우세무", r"후이즈", r"다우데이타", r"쿠콘", r"보라웨어",
             r"네이버클라우드", r"주오컴퍼니", r"에이티링크", r"KCP"],
            [r"세무법인", r"지우세무", r"회계법인", r"법무법인",
             r"후이즈", r"다우데이타", r"쿠콘", r"보라웨어",
             r"네이버클라우드", r"주오컴퍼니"], sign="-", section="IV_sga"),
    Account("8220", "광고선전비",
            [r"광고비", r"홍보비", r"마케팅비용", r"검색광고비",
             r"배너광고", r"sns광고비", r"현수막제작", r"홍보용품",
             r"네이버파이낸셜", r"네이버페이"],
            [r"네이버", r"카카오광고", r"구글광고", r"메타",
             r"페이스북", r"인스타그램"], sign="-", section="IV_sga"),
    Account("8230", "건물관리비",
            [r"건물관리비", r"시설관리비", r"청소용역비", r"경비용역비",
             r"매장인테리어", r"인테리어잔금"],
            [r"효성에프엠에스", r"에스원", r"시티파크"], sign="-", section="IV_sga"),

    # ── 영업외수익 ────────────────────────────────────────────────────────────
    Account("9010", "이자수익",
            [r"이자수익", r"예금이자", r"적금이자", r"정기예금.*이자",
             r"이자수입", r"예금결산"],
            [], sign="+", section="VI_non_op_revenue"),
    Account("9020", "유형자산처분이익",
            [r"유형자산처분", r"자산매각", r"자산처분이익", r"매각이익"],
            [], sign="+", section="VI_non_op_revenue"),
    Account("9030", "잡이익",
            [r"잡이익", r"기타수익", r"잡수입", r"환차익", r"보험수령"],
            [], sign="+", section="VI_non_op_revenue"),

    # ── 영업외비용 ────────────────────────────────────────────────────────────
    Account("9110", "이자비용",
            [r"대출이자", r"이자납부", r"이자비용", r"차입금이자",
             r"중진공대출", r"대출원리", r"이자지급",
             r"대출.*이자", r"연체이자"],
            [r"중소벤처기업진흥공단", r"중진공", r"국민은행", r"신한은행",
             r"우리은행", r"하나은행", r"IBK기업은행", r"농협은행",
             r"기업은행"], sign="-", section="VII_non_op_expense"),
    Account("9120", "전기오류수정손실",
            [r"전기오류", r"오류수정", r"전기수정"],
            [], sign="-", section="VII_non_op_expense"),
    Account("9130", "잡손실",
            [r"잡비", r"기타잡비", r"잡손실", r"기타비용", r"잡급"],
            [], sign="-", section="VII_non_op_expense"),

    # ── 특수 ─────────────────────────────────────────────────────────────────
    Account("9999", "미분류",
            [],  # 다른 계정과목에 미매칭 시 fallback
            [], sign="+", section="other"),
]

# 이름 → Account 빠른 조회
ACCOUNT_BY_NAME: dict[str, Account] = {a.name: a for a in ACCOUNTS}
ACCOUNT_BY_CODE: dict[str, Account] = {a.code: a for a in ACCOUNTS}

# 미리 컴파일된 패턴 (결정적 분류를 위해 모듈 로딩 시 1회만 컴파일)
_COMPILED: List[Tuple[Account, List[re.Pattern[str]], List[re.Pattern[str]]]] = []

def _build_compiled() -> None:
    for acc in ACCOUNTS:
        kw_patterns = [re.compile(p, re.IGNORECASE) for p in acc.keywords]
        vd_patterns = [re.compile(p, re.IGNORECASE) for p in acc.vendor_patterns]
        _COMPILED.append((acc, kw_patterns, vd_patterns))

_build_compiled()


def match_account(description: str, vendor: str = "") -> Tuple[str, float]:
    """거래 내용(description)과 거래처(vendor)로 계정과목 반환.

    Returns:
        (account_name, confidence) — confidence: 0.0~1.0
    """
    description = description or ""
    vendor = vendor or ""
    combined = description + " " + vendor

    best_name = "미분류"
    best_score = 0.0
    best_conf = 0.0

    for acc, kw_pats, vd_pats in _COMPILED:
        if acc.name == "미분류":
            continue

        if not kw_pats and not vd_pats:
            continue

        kw_hit = sum(1 for p in kw_pats if p.search(description))
        vd_hit = sum(1 for p in vd_pats if p.search(combined))

        if kw_hit == 0 and vd_hit == 0:
            continue

        raw = kw_hit * 1.0 + vd_hit * 0.5

        # 신뢰도 계산 — 동점 비교에서도 참조하므로 비교 전 산출
        if kw_hit > 0:
            kw_ratio = kw_hit / max(1, len(kw_pats))
            conf = min(1.0, 0.50 + kw_ratio * 0.40 + (0.10 if vd_hit > 0 else 0.0))
        else:
            # 벤더 단독 매칭: 임계값 미만 — 미분류로 격리됨
            conf = 0.30

        # 동점(raw==best_score) 시 신뢰도가 높은 쪽 선택 — vendor-only 잠김 방지
        if raw > best_score or (raw == best_score and conf > best_conf):
            best_score = raw
            best_conf = conf
            best_name = acc.name

    # 50% 미만 신뢰도는 미분류로 격리
    if best_conf < 0.50:
        return "미분류", 0.0

    return best_name, round(best_conf, 3)
