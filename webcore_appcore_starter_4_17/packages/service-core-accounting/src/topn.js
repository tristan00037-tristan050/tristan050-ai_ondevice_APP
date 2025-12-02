/**
 * Top-N 후보 확장 및 스코어링
 * 기존 매핑 결과를 보존하면서 Top-N을 풍부하게 만들어 Top-5 개선
 *
 * @module service-core-accounting/topn
 */
import * as mapping from './mapping.js';
function tokenize(s) {
    if (!s)
        return [];
    return s.toLowerCase()
        .replace(/[^\p{L}\p{N}\s]/gu, ' ')
        .split(/\s+/).filter(Boolean);
}
function amountBucket(amtKRW) {
    if (amtKRW <= 5_000)
        return 'micro';
    if (amtKRW <= 30_000)
        return 'small';
    if (amtKRW <= 150_000)
        return 'mid';
    if (amtKRW <= 1_000_000)
        return 'large';
    return 'xl';
}
function uniq(arr) {
    const seen = new Set();
    return arr.filter((x) => {
        const k = typeof x === 'string' ? x : JSON.stringify(x);
        if (seen.has(k))
            return false;
        seen.add(k);
        return true;
    });
}
// 기본 풀: mapping 쪽에서 노출되는 키를 우선 사용, 없으면 합리적 디폴트
const DEFAULT_POOL = [
    '5010', // 사무용품비
    '6010', // 교통비
    '6020', // 접대비
    '6030', // 통신비
    '6040', // 임대료
    '6050', // 급여
    '6060', // 수도광열비
    '6070', // 보험료
    '6080', // 세금과공과
    '6090', // 수수료비용
];
// 계정 코드와 키워드 매핑
const ACCOUNT_KEYWORDS = {
    '5010': ['사무용품', '문구', '복사지', '프린터', '컴퓨터'],
    '6010': ['택시', '지하철', '버스', '교통', '주유', '주차'],
    '6020': ['식대', '접대', '커피', '스타벅스', '식사', '회식'],
    '6030': ['통신', '전화', '인터넷', '휴대폰', '통신비'],
    '6040': ['임대', '월세', '전세', '임대료'],
    '6050': ['급여', '월급', '보수', '인건비'],
    '6060': ['수도', '전기', '가스', '광열', '공과금'],
    '6070': ['보험', '보험료', '건강보험'],
    '6080': ['세금', '공과', '세금과공과'],
    '6090': ['수수료', '수수료비용', '은행수수료'],
};
function accountPool() {
    return Object.keys(ACCOUNT_KEYWORDS).length > 0 ? Object.keys(ACCOUNT_KEYWORDS) : DEFAULT_POOL;
}
// 키워드 히트 기반 후보 생성
function keywordCandidates(desc) {
    const toks = new Set(tokenize(desc));
    const pool = accountPool();
    const out = [];
    for (const code of pool) {
        const kws = ACCOUNT_KEYWORDS[code] ?? [];
        if (!kws.length)
            continue;
        const hits = kws.filter(k => toks.has(k.toLowerCase())).length;
        if (hits > 0) {
            out.push({
                code,
                score: 0.6 + 0.05 * hits,
                reasons: [`kw_hits=${hits}`]
            });
        }
    }
    return out.sort((a, b) => b.score - a.score);
}
// 금액 버킷 기반 백업 후보
function bucketFallbacks(amtKRW) {
    const b = amountBucket(amtKRW);
    const pool = accountPool();
    const prefer = {
        micro: ['6020', '5010', '6010'], // 커피, 사무용품, 교통비
        small: ['6020', '5010', '6030'], // 식대, 사무용품, 통신비
        mid: ['6060', '6090', '6070'], // 수도광열비, 수수료, 보험료
        large: ['6040', '6060', '6090'], // 임대료, 수도광열비, 수수료
        xl: ['6080', '6040', '6090'] // 세금과공과, 임대료, 수수료
    };
    const codes = prefer[b]?.filter(code => pool.includes(code)) ?? [];
    return codes.map((code, i) => ({
        code,
        score: 0.35 - i * 0.02,
        reasons: [`bucket=${b}`]
    }));
}
// 매핑 함수가 있으면 존중
function mappedPrimary(desc) {
    const mapped = mapping.mapAccount(desc);
    if (!mapped)
        return [];
    return [{
            code: mapped,
            score: 0.9,
            reasons: ['mapping']
        }];
}
// 최종 후보 확장기 (Top-N 풍부화)
export function expandAndRankCandidates(desc, amtKRW, topN = 8) {
    const cands = [
        ...mappedPrimary(desc),
        ...keywordCandidates(desc),
        ...bucketFallbacks(amtKRW)
    ];
    // 중복 제거 (같은 code는 최고 점수만 유지)
    const dedupMap = new Map();
    for (const cand of cands) {
        const existing = dedupMap.get(cand.code);
        if (!existing || cand.score > existing.score) {
            dedupMap.set(cand.code, cand);
        }
    }
    const dedup = Array.from(dedupMap.values()).sort((a, b) => b.score - a.score);
    return dedup.slice(0, topN);
}
//# sourceMappingURL=topn.js.map