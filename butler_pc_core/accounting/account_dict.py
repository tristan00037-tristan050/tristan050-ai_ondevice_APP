"""KIFRS 회계과목 사전 — 30개 계정과목별 정규식 패턴."""
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


# 패턴 우선순위: 목록 순서대로 매칭, 첫 번째 명중 계정 반환 (결정적)
ACCOUNTS: List[Account] = [
    # ── 수익 ────────────────────────────────────────────────────────────────
    Account("4010", "매출",
            [r"매출", r"판매수입", r"용역수입", r"서비스수입", r"수입금액"],
            []),
    Account("4020", "이자수익",
            [r"이자수익", r"예금이자", r"적금이자", r"정기예금.*이자", r"이자수입"],
            []),

    # ── 비용 (판매관리비) ────────────────────────────────────────────────────
    Account("8110", "급여",
            [r"급여", r"임금", r"월급", r"봉급", r"인건비지급"],
            []),
    Account("8120", "상여금",
            [r"상여금", r"인센티브", r"성과급", r"특별상여"],
            []),
    Account("8130", "복리후생비",
            [r"복리후생", r"식대보조", r"중식비", r"석식비", r"회식비",
             r"건강검진비", r"경조금", r"명절선물", r"생일선물"],
            []),
    Account("8140", "여비교통비",
            [r"여비교통", r"출장비", r"항공료", r"철도요금", r"택시비",
             r"버스요금", r"고속도로.*통행료", r"주차료"],
            []),
    Account("8150", "접대비",
            [r"접대비", r"거래처.*식사", r"거래처.*선물", r"골프.*비용",
             r"접대.*비용"],
            []),
    Account("8160", "통신비",
            [r"통신비", r"이동통신요금", r"인터넷요금", r"전화요금",
             r"휴대폰요금"],
            ["KT", "SKT", "SK텔레콤", "LGU\\+", "LG유플러스", "SK브로드밴드"]),
    Account("8170", "수도광열비",
            [r"수도요금", r"전기요금", r"도시가스요금", r"가스요금",
             r"전력요금", r"열요금"],
            ["한국전력", "한전", "도시가스", "서울도시가스", "코원에너지"]),
    Account("8180", "세금과공과",
            [r"부가가치세", r"법인세납부", r"소득세납부", r"재산세",
             r"취득세", r"지방세납부", r"주민세", r"과태료"],
            ["국세청", "세무서", "지방자치단체"]),
    Account("8190", "임차료",
            [r"임차료", r"임대료납부", r"사무실임대", r"월세납부",
             r"공간임차"],
            []),
    Account("8200", "감가상각비",
            [r"감가상각", r"상각비"],
            []),
    Account("8210", "보험료",
            [r"보험료납부", r"화재보험", r"자동차보험", r"배상책임보험",
             r"산재보험료", r"고용보험료", r"건강보험료", r"국민연금보험료"],
            ["삼성화재", "현대해상", "DB손해보험", "KB손해보험", "메리츠화재"]),
    Account("8220", "차량유지비",
            [r"주유비", r"경유구매", r"휘발유구매", r"엔진오일교환",
             r"차량수리비", r"타이어교체", r"세차비", r"차량유지"],
            ["SK에너지", "GS칼텍스", "현대오일뱅크", "S-OIL", "알뜰주유소"]),
    Account("8230", "교육훈련비",
            [r"교육비", r"연수비", r"세미나참가비", r"워크숍비용",
             r"자격증취득비", r"강의료", r"훈련비"],
            []),
    Account("8240", "도서인쇄비",
            [r"도서구입", r"서적구매", r"인쇄비", r"복사비",
             r"출판비", r"문서출력비"],
            []),
    Account("8250", "소모품비",
            [r"소모품구입", r"사무용품비", r"문구류구입", r"복사지구매",
             r"토너구입", r"잉크구매"],
            []),
    Account("8260", "지급수수료",
            [r"수수료지급", r"컨설팅비", r"자문료", r"대행수수료",
             r"법무비용", r"세무자문비", r"노무자문비", r"변호사비용"],
            []),
    Account("8270", "광고선전비",
            [r"광고비", r"홍보비", r"마케팅비용", r"검색광고비",
             r"배너광고", r"sns광고비", r"현수막제작"],
            ["네이버광고", "카카오광고", "구글광고"]),
    Account("8280", "잡비",
            [r"잡비", r"기타잡비", r"잡급"],
            []),

    # ── 매입원가 ─────────────────────────────────────────────────────────────
    Account("5010", "상품매입",
            [r"상품매입", r"물품구매", r"원재료구입", r"자재구매",
             r"부품구입", r"재고구매"],
            []),

    # ── 부채 ─────────────────────────────────────────────────────────────────
    Account("2510", "단기차입금",
            [r"단기차입금", r"당좌차월", r"기업대출이자", r"대출이자납부",
             r"차입금상환"],
            ["국민은행", "신한은행", "우리은행", "하나은행", "기업은행",
             "농협은행", "IBK기업은행"]),
    Account("2520", "장기차입금",
            [r"장기차입금", r"시설자금대출", r"장기대출원금", r"장기이자납부"],
            []),
    Account("2530", "미지급금",
            [r"미지급금납부", r"외상매입금결제", r"구매대금결제"],
            []),

    # ── 자산 ─────────────────────────────────────────────────────────────────
    Account("1010", "보통예금",
            [r"보통예금입금", r"계좌이체.*입금", r"이체수취"],
            []),
    Account("1110", "외상매출금",
            [r"외상매출금회수", r"매출채권회수", r"거래대금수령"],
            []),
    Account("1510", "비품",
            [r"비품구입", r"사무기기구입", r"컴퓨터구매", r"프린터구매",
             r"복합기구매"],
            []),
    Account("1520", "차량운반구",
            [r"차량구입", r"법인차량구매", r"업무용차량취득"],
            []),

    # ── 자본 ─────────────────────────────────────────────────────────────────
    Account("3010", "자본금",
            [r"자본금납입", r"출자금", r"증자금"],
            []),

    # ── 특수 ─────────────────────────────────────────────────────────────────
    Account("9000", "미분류",
            [],  # 다른 계정과목에 미매칭 시 fallback
            []),
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

        # 신뢰도 계산 (동점 비교에서도 사용하므로 비교 전에 산출)
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
