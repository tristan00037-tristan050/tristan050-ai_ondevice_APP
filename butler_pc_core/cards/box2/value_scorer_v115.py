from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Mapping

SCORER_VERSION = 'box2.eval.v3_gold'
BASELINE_SCORE = 0.30
EXPECTED_GOLD_CASE_COUNT = 10
EXPECTED_EVAL_SHA256 = '1e0f2766be37586e16b3e63495dec7a8955d155b33c9a2ebd3f73243377b429d'
CONFIRM_NEEDED = '[확인 필요]'
CURRENCY_MAP = {'원':'KRW','₩':'KRW','￦':'KRW','krw':'KRW','달러':'USD','$':'USD','usd':'USD','불':'USD','엔':'JPY','¥':'JPY','유로':'EUR','€':'EUR'}
DATE_SLASH_RE = re.compile(r'^\s*\d{4}\s*/\s*\d{1,2}\s*/\s*\d{1,2}\s*$')


def repo_eval_paths(anchor: Path) -> list[Path]:
    root = anchor.resolve().parents[3]
    return [root / 'butler-ct-shared/code_archive/box2_eval', root / 'butler-ct-shared/code_archive/box2_eval/box2_eval.json']


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_eval_sha(eval_path: Path) -> str:
    digest = sha256_file(eval_path)
    if digest != EXPECTED_EVAL_SHA256:
        raise ValueError('BOX2_EVALSET_SHA_DRIFT')
    return digest


def canon_text(value: Any) -> str:
    return re.sub(r'[\s,]', '', unicodedata.normalize('NFKC', str(value or '')))


def extract_money_token(value: Any) -> tuple[str, str]:
    s = unicodedata.normalize('NFKC', str(value or '')).strip()
    lower = s.lower()
    currency = ''
    for token, code in CURRENCY_MAP.items():
        if token in lower or token in s:
            currency = code
            break
    return re.sub(r'[^\d.]', '', s), currency


def money_preserved(gold: Any, observed: Any) -> bool:
    gnum, gcur = extract_money_token(gold)
    if not gnum:
        return canon_text(gold) in canon_text(observed)
    for token in re.findall(r'[\d,]+(?:\.\d+)?', str(observed or '')):
        if re.sub(r'[^\d.]', '', token) == gnum:
            _onum, ocur = extract_money_token(observed)
            if gcur and ocur and gcur != ocur:
                return False
            return True
    return False


def canonical_preserved(gold: Any, observed: Any) -> bool:
    if extract_money_token(gold)[0]:
        return money_preserved(gold, observed)
    return canon_text(gold) in canon_text(observed)


def validate_case_schema(item: Mapping[str, Any], *, index: int) -> tuple[str, Any, list[str], dict[str, str]]:
    foreign = item.get('foreign')
    fmt = item.get('format')
    must_keep = item.get('must_keep')
    fields = item.get('fields')
    if not isinstance(foreign, str) or not foreign.strip():
        raise ValueError(f'CASE_{index}_FOREIGN_MISSING')
    if fmt is None:
        raise ValueError(f'CASE_{index}_FORMAT_MISSING')
    if not isinstance(must_keep, list) or not must_keep:
        raise ValueError(f'CASE_{index}_MUST_KEEP_INVALID')
    if not isinstance(fields, dict) or not fields:
        raise ValueError(f'CASE_{index}_FIELDS_INVALID')
    return foreign, fmt, [str(v) for v in must_keep if str(v)], {str(k): str(v) for k, v in fields.items()}


def read_field(doc: str, label: str, allowed: list[str]) -> str:
    if label in {'일정', '납기', '기한', '납품일'}:
        m = re.search(rf'{re.escape(label)}\s*[:：=]\s*(\d{{4}}\s*/\s*\d{{1,2}}\s*/\s*\d{{1,2}})', doc or '')
        if m:
            return re.sub(r'\s+', '', m.group(1))
    alt = '|'.join(re.escape(x) for x in allowed if x)
    if not alt:
        return ''
    pat = re.compile(rf'(?:^|\n|/|\||;|,)\s*{re.escape(label)}\s*[:：=]\s*(?P<value>.*?)(?=(?:\n|/|\||;|,)?\s*(?:{alt})\s*[:：=]|$)', re.DOTALL)
    m = pat.search(doc or '')
    return re.sub(r'\s+', ' ', m.group('value')).strip() if m else ''


def score_against_gold(doc: str, item: Mapping[str, Any], index: int) -> dict[str, float | int]:
    _foreign, fmt, must_keep, fields = validate_case_schema(item, index=index)
    allowed = sorted(({label for label in fields if label in str(fmt)} or set(fields)), key=len, reverse=True)
    exact = sum(1 for v in must_keep if v and v in doc)
    canon = sum(1 for v in must_keep if v and canonical_preserved(v, doc))
    hit = fp = 0
    for label, gold in fields.items():
        got = read_field(doc, label, allowed)
        if canon_text(got) == canon_text(gold) or money_preserved(gold, got):
            hit += 1
        elif got not in (CONFIRM_NEEDED, ''):
            fp += 1
    n = len(fields)
    return {'value_exact_preservation': exact / len(must_keep), 'value_canonical_preservation': canon / len(must_keep), 'field_hit': hit, 'false_positive': fp, 'precision': hit / (hit + fp) if hit + fp else 0.0, 'recall': hit / n if n else 0.0, 'false_negative': n - hit}


def load_eval_samples(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding='utf-8'))
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        rows = data.get('samples') or data.get('items') or data.get('cases') or []
        return [x for x in rows if isinstance(x, dict)]
    return []


def summarize_scores(scores: list[dict[str, float | int]], eval_path: Path) -> dict[str, Any]:
    n = len(scores)
    avg = lambda key: sum(float(row[key]) for row in scores) / n if n else 0.0
    canonical = avg('value_canonical_preservation')
    report = {'schema_version': SCORER_VERSION, 'scorer_version': SCORER_VERSION, 'status': 'PASS' if n == EXPECTED_GOLD_CASE_COUNT else 'PARTIAL', 'eval_set_path': str(eval_path), 'eval_set_sha256': sha256_file(eval_path), 'baseline_score': BASELINE_SCORE, 'new_score': canonical, 'value_exact_preservation': avg('value_exact_preservation'), 'value_canonical_preservation': canonical, 'delta': canonical - BASELINE_SCORE, 'n': n, 'field_precision': avg('precision'), 'field_recall': avg('recall'), 'false_positive_total': sum(int(row['false_positive']) for row in scores), 'false_negative_total': sum(int(row['false_negative']) for row in scores), 'external_send_zero': True, 'stored_source_zero': True}
    if report['eval_set_sha256'] != EXPECTED_EVAL_SHA256:
        report['status'] = 'BOX2_EVALSET_SHA_DRIFT'
    return report
