from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from .grounded_prompt import FORBIDDEN_LABELS, REQUIRED_LABELS
from .v7_fail_class import BLOCK_DEGENERATION_DETECTED, BLOCK_RAW_OR_PATH_EVIDENCE_LEAK

# Fusion v1.3: MAINDEV format-structure detection (label loop / forbidden label /
# prompt-marker leak / too-short) UNION ALG content-leak detection
# (repeated-line / JSON-or-tool branch / path-or-secret leak).
# Single function, both capabilities. raw/path leak takes precedence (security first).

_JSON_OR_TOOL_RE = re.compile(r"```json|\{\s*\"(?:completion|tool|meeting|arguments)\"|tool_call", re.I)
_PATH_OR_SECRET_RE = re.compile(r"/Users/|/home/|/Volumes/|sk-proj-|BEGIN PRIVATE KEY|api_key", re.I)
_PROMPT_MARKERS = ("OUTPUT_FORMAT_STRICT", "SYSTEM:", "[근거 DIGEST MARKERS]", "<|im_start|>", "<|im_end|>")


@dataclass(frozen=True)
class DegenerationVerdict:
    detected: bool
    fail_class: str | None
    ngram_ratio: float
    repeated_label_detected: bool
    repeated_line_count: int
    prompt_marker_leak: bool
    json_or_tool_leak: bool
    raw_or_path_leak: bool
    too_short: bool
    forbidden_label_detected: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _ngram_ratio(tokens: list[str], n: int = 4) -> float:
    if len(tokens) < n:
        return 0.0
    grams = [tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1)]
    return 1.0 - (len(set(grams)) / max(1, len(grams)))


def evaluate_degeneration(draft_text: str, *, ngram_threshold: float = 0.18) -> DegenerationVerdict:
    tokens = re.findall(r"[A-Za-z가-힣0-9_\[\]<>|]+", draft_text)
    ratio = round(_ngram_ratio(tokens), 4)

    # MAINDEV: label-structure checks (OUTPUT_FORMAT_STRICT integrity)
    labels = re.findall(r"^(.*?):", draft_text, flags=re.M)
    repeated_label = any(labels.count(label) > 1 for label in labels)
    forbidden = any(label in draft_text for label in FORBIDDEN_LABELS)
    prompt_marker_leak = any(marker in draft_text for marker in _PROMPT_MARKERS)
    too_short = len(tokens) < 12

    # ALG: content-leak checks (repeated lines / JSON-tool branch / raw-path-secret)
    lines = [line.strip() for line in draft_text.splitlines() if line.strip()]
    seen: dict[str, int] = {}
    repeated_line_count = 0
    for line in lines:
        seen[line] = seen.get(line, 0) + 1
        if seen[line] == 3:
            repeated_line_count += 1
    json_or_tool_leak = bool(_JSON_OR_TOOL_RE.search(draft_text))
    raw_or_path_leak = bool(_PATH_OR_SECRET_RE.search(draft_text))

    # Security-first precedence: raw/path/secret leak is the hardest fail.
    if raw_or_path_leak:
        return DegenerationVerdict(
            True, BLOCK_RAW_OR_PATH_EVIDENCE_LEAK, ratio, repeated_label,
            repeated_line_count, prompt_marker_leak, json_or_tool_leak,
            raw_or_path_leak, too_short, forbidden,
        )

    detected = (
        ratio > ngram_threshold
        or repeated_label
        or repeated_line_count > 0
        or forbidden
        or prompt_marker_leak
        or json_or_tool_leak
        or too_short
    )
    return DegenerationVerdict(
        detected, BLOCK_DEGENERATION_DETECTED if detected else None, ratio, repeated_label,
        repeated_line_count, prompt_marker_leak, json_or_tool_leak,
        raw_or_path_leak, too_short, forbidden,
    )
