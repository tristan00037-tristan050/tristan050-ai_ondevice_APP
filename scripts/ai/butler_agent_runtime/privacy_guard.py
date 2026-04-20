from __future__ import annotations

import hashlib
import re
from .runtime_contracts import ScanResult

_PATTERNS = {
    'rrn': re.compile(r'\b\d{6}-\d{7}\b'),
    'card': re.compile(r'\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b'),
    'phone': re.compile(r'\b01[0-9]-\d{3,4}-\d{4}\b'),
    'biz': re.compile(r'\b\d{3}-\d{2}-\d{5}\b'),
    'account': re.compile(r'(?<!\d)(?:\d{2,4}-\d{2,6}-\d{2,8}|\d{8,14})(?!\d)'),
    'email': re.compile(r'[\w.-]+@[\w.-]+\.\w+'),
    'passport': re.compile(r'\b[A-Z]{1,2}\d{7,8}\b'),
}


def _digest16(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]


def mask(text: str) -> str:
    # order matters: more specific before more general
    text = _PATTERNS['rrn'].sub(lambda m: m.group(0)[:8] + '******', text)
    text = _PATTERNS['card'].sub(lambda m: re.sub(r'\D', '', m.group(0))[:4] + '-****-****-' + re.sub(r'\D', '', m.group(0))[-4:], text)
    text = _PATTERNS['phone'].sub(lambda m: m.group(0)[:4] + '-****-' + m.group(0)[-4:], text)
    text = _PATTERNS['email'].sub('[EMAIL]', text)
    text = _PATTERNS['biz'].sub('[BIZ]', text)
    text = _PATTERNS['passport'].sub('[PASSPORT]', text)
    text = _PATTERNS['account'].sub('[ACCOUNT]', text)
    return text


def scan(text: str) -> ScanResult:
    hit_types: list[str] = []
    for name, pat in _PATTERNS.items():
        if pat.search(text):
            hit_types.append(name)
    masked = mask(text)
    return ScanResult(bool(hit_types), hit_types, masked, _digest16(masked), len(masked))
