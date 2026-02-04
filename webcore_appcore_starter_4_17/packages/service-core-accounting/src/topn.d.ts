/**
 * Top-N 후보 확장 및 스코어링
 * 기존 매핑 결과를 보존하면서 Top-N을 풍부하게 만들어 Top-5 개선
 *
 * @module service-core-accounting/topn
 */
export type Candidate = {
    code: string;
    score: number;
    reasons: string[];
};
export declare function expandAndRankCandidates(desc: string, amtKRW: number, topN?: number): Candidate[];
//# sourceMappingURL=topn.d.ts.map