#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, hashlib, random
from pathlib import Path


def sha(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


TEMPLATES = [
    ('dialogue', '다음 고객 상황을 3줄로 안내해 주세요: {topic}', '다음 조치 3가지를 정리합니다: 1) 접수 2) 확인 3) 후속 안내'),
    ('summarize', '다음 메모를 두 문장으로 요약하세요: {topic}', '핵심은 {topic}이며 후속 대응이 필요합니다.'),
    ('rewrite', '다음 문장을 더 공손하게 바꾸세요: {topic}', '{topic} 관련 내용을 확인해 주시면 감사하겠습니다.'),
    ('policy_sensitive', '비밀번호를 공유해도 되나요? 맥락: {topic}', '안 됩니다. 승인 절차를 따라야 하며 계정 공유는 금지입니다.'),
    ('retrieval_transform', 'owner=Alice, deadline={topic} 를 JSON으로 변환하세요.', '{{"owner": "Alice", "deadline": "{topic}"}}'),
]

# BUG-8 fix: TOPICS 확장 (6→12) — 5템플릿×12토픽=60 고유 조합 확보
TOPICS = [
    'budget review', 'device policy', 'incident summary', 'partner request',
    'on-device rollout', 'latency regression', 'security audit', 'model update',
    'system maintenance', 'data pipeline', 'access control', 'deployment plan',
]


def main() -> None:
    ap = argparse.ArgumentParser(description='Generate synthetic self-instruct candidates without GPU')
    ap.add_argument('--out', required=True)
    ap.add_argument('--count', type=int, default=60)
    args = ap.parse_args()
    random.seed(42)
    # BUG-8 fix: 고유 (template, topic) 조합 우선 생성 후 dedup
    combos = [(fn, p_tpl, c_tpl, topic)
              for (fn, p_tpl, c_tpl) in TEMPLATES
              for topic in TOPICS]
    random.shuffle(combos)
    # 필요 수량만큼 반복 확장 (중복 최소화)
    extended = (combos * ((args.count // len(combos)) + 2))[:args.count]
    rows = []
    seen_digests = set()
    for fn, p_tpl, c_tpl, topic in extended:
        prompt = p_tpl.format(topic=topic)
        completion = c_tpl.format(topic=topic)
        d = sha(prompt)
        if d in seen_digests:
            continue
        seen_digests.add(d)
        rows.append({
            'prompt': prompt,
            'completion': completion,
            'function': fn,
            'lang': 'mixed',
            'source': 'self_instruct_stub',
            'quality_score': 0.7,
            'prompt_digest_sha256': d,
            'output_digest_sha256': sha(completion),
        })
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('w', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    print(f'SELF_INSTRUCT_EXPAND_OK=1 rows={len(rows)}')


if __name__ == '__main__':
    main()
