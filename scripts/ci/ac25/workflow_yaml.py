"""GitHub Actions 워크플로를 ★표준 라이브러리만으로★ 읽는 좁은 파서.

왜 PyYAML 을 쓰지 않는가
  canonical 계획 추출은 ★신뢰 경로★ 다. 저장소 계약을 exact head 에서 돌리는
  job 이 이 코드를 부른다. 거기에 외부 패키지를 끌어들이면
    · 공급망 표면이 늘고
    · hash-locked 설치 계약(dependency manifest)을 함께 건드려야 하고
    · 설치가 빠진 환경에서 ★검증기가 아예 실행되지 않는다.★
  마지막 것이 실제로 일어났다 — 원격에서 `ModuleNotFoundError: No module named
  'yaml'` 로 job 이 죽었다. 실행되지 않는 검증기는 검증기가 아니다.

무엇을 파싱하는가
  ★일반 YAML 을 다루지 않는다★. 이 저장소 워크플로가 실제로 쓰는 부분집합만
  읽고, 그 밖의 문법을 만나면 ★추측하지 않고 닫는다★(fail-closed).

    맵          key: value
    중첩 맵     들여쓰기
    시퀀스      "- " 로 시작하는 항목(맵 또는 스칼라)
    블록 스칼라 `|` `|-` `>` `>-`
    인용        "..."  '...'
    주석        인용 밖의 `#`

  앵커·별칭·흐름 컬렉션(`{}` `[]`)·복수 문서·태그는 ★지원하지 않고 닫는다★.
  지원하는 척하다 조용히 틀리게 읽는 것이 가장 나쁘다.

정확성은 어떻게 보장하는가
  시험이 같은 파일을 PyYAML 로도 읽어 ★결과가 완전히 같은지★ 대조한다.
  PyYAML 은 시험에만 있고 production 에는 없다.
"""
from __future__ import annotations

import re as _re
from dataclasses import dataclass

WORKFLOW_YAML_UNSUPPORTED = "WORKFLOW_YAML_UNSUPPORTED"
WORKFLOW_YAML_MALFORMED = "WORKFLOW_YAML_MALFORMED"

_BLOCK_MARKERS = ("|", "|-", "|+", ">", ">-", ">+")
# 지원하지 않는 YAML 문법. 만나면 닫는다.
_UNSUPPORTED_STARTS = ("&", "*", "!", "? ", "--- ", "%")


class WorkflowYamlError(Exception):
    """메시지에 코드와 줄 번호만 담는다. 원문을 담지 않는다."""

    def __init__(self, code: str, line_number: int = 0) -> None:
        super().__init__(f"{code}@{line_number}" if line_number else code)
        self.code = code
        self.line_number = line_number


@dataclass(frozen=True)
class _Line:
    number: int
    indent: int
    text: str


def _strip_comment(raw: str) -> str:
    """인용 밖의 `#` 부터 잘라낸다. 인용 안의 `#` 는 값이다."""
    out: list[str] = []
    quote: str | None = None
    previous = ""
    for index, char in enumerate(raw):
        if quote is None and char == "#":
            # `#` 앞이 공백이거나 줄 처음일 때만 주석이다(예: `a#b` 는 값)
            if index == 0 or previous in (" ", "\t"):
                break
            out.append(char)
        elif quote is None and char in ("'", '"'):
            quote = char
            out.append(char)
        elif quote is not None and char == quote:
            quote = None
            out.append(char)
        else:
            out.append(char)
        previous = char
    return "".join(out).rstrip()


def _split_flow(body: str, line_number: int) -> list[str]:
    """흐름 컬렉션 안을 쉼표로 나눈다.

    ★인용 안의 `,` 와 `{}` 는 값이다★. 워크플로는 `{python-version: '${{ env.X }}'}`
      처럼 인용 안에 표현식 중괄호를 담는다. 그것을 중첩으로 오해하면 안 된다.
    ★인용 밖의 중첩 흐름은 닫는다 — 이 저장소가 쓰지 않는다.
    """
    parts: list[str] = []
    current: list[str] = []
    quote: str | None = None
    for char in body:
        if quote is None and char in ("'", '"'):
            quote = char
        elif quote is not None and char == quote:
            quote = None
        elif quote is None and char in "[]{}":
            raise WorkflowYamlError(WORKFLOW_YAML_UNSUPPORTED, line_number)
        elif quote is None and char == ",":
            parts.append("".join(current).strip())
            current = []
            continue
        current.append(char)
    if quote is not None:
        raise WorkflowYamlError(WORKFLOW_YAML_MALFORMED, line_number)
    tail = "".join(current).strip()
    if tail:
        parts.append(tail)
    return parts


def _flow_collection(text: str, line_number: int):
    """`[a, b]` · `{a: b}` 같은 ★한 줄짜리★ 흐름 컬렉션만 읽는다.

    워크플로가 `needs: [job-a, job-b]` 형태를 흔히 쓴다. 중첩 흐름은 닫는다 —
    이 저장소가 쓰지 않고, 잘못 읽느니 멈추는 편이 낫다.
    """
    if text.startswith("[") and text.endswith("]"):
        return [_scalar(part, line_number) for part in _split_flow(text[1:-1], line_number)]
    if text.startswith("{") and text.endswith("}"):
        found: dict = {}
        for part in _split_flow(text[1:-1], line_number):
            if ":" not in part:
                raise WorkflowYamlError(WORKFLOW_YAML_MALFORMED, line_number)
            key, _, value = part.partition(":")
            found[_scalar(key, line_number)] = _scalar(value, line_number)
        return found
    raise WorkflowYamlError(WORKFLOW_YAML_UNSUPPORTED, line_number)


def _scalar(token: str, line_number: int) -> str:
    """스칼라 하나를 읽는다. 인용을 벗기고, 지원 못 하는 문법은 닫는다."""
    text = token.strip()
    if not text:
        return ""
    if text.startswith(_UNSUPPORTED_STARTS):
        raise WorkflowYamlError(WORKFLOW_YAML_UNSUPPORTED, line_number)
    if text.startswith(("{", "[")):
        # 스칼라 자리에 흐름 컬렉션이 왔다 — 호출부(_value)가 처리해야 한다
        raise WorkflowYamlError(WORKFLOW_YAML_UNSUPPORTED, line_number)
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
        inner = text[1:-1]
        if text[0] == '"':
            # 워크플로에서 쓰는 최소 이스케이프만 푼다
            inner = inner.replace('\\"', '"').replace("\\\\", "\\").replace("\\n", "\n")
        else:
            inner = inner.replace("''", "'")
        return inner  # ★인용된 값은 언제나 문자열이다
    return _typed(text)


# YAML 1.1 이 bool 로 읽는 표기(PyYAML safe_load 와 같은 집합)
_TRUE = frozenset({"true", "True", "TRUE", "yes", "Yes", "YES", "on", "On", "ON", "y", "Y"})
_FALSE = frozenset({"false", "False", "FALSE", "no", "No", "NO", "off", "Off", "OFF", "n", "N"})
_NULL = frozenset({"null", "Null", "NULL", "~", ""})


# ★PyYAML(safe_load) 의 resolver 정규식을 그대로 옮긴다.
#   느슨하게 읽으면 PyYAML 이 문자열로 두는 값을 숫자로 바꾼다 — 실제로
#   `1e-6` 에서 그 일이 났다. YAML 1.1 float 은 지수부에 ★부호가 필수★ 이고
#   소수점이 있어야 한다. `1e-6` 은 float 이 아니라 문자열이다.
_INT_RE = _re.compile(
    r"""\A[-+]?(?:0b[0-1_]+
    |0[0-7_]+
    |(?:0|[1-9][0-9_]*)
    |0x[0-9a-fA-F_]+
    |[1-9][0-9_]*(?::[0-5]?[0-9])+)\Z""",
    _re.X,
)
_FLOAT_RE = _re.compile(
    r"""\A(?:[-+]?(?:[0-9][0-9_]*)\.[0-9_]*(?:[eE][-+][0-9]+)?
    |\.[0-9_]+(?:[eE][-+][0-9]+)?
    |[-+]?[0-9][0-9_]*(?::[0-5]?[0-9])+\.[0-9_]*
    |[-+]?\.(?:inf|Inf|INF)
    |\.(?:nan|NaN|NAN))\Z""",
    _re.X,
)


# YAML 1.1 은 인용 없는 `2026-08-06` 을 ★date 객체★ 로 읽는다. 이 파서는 날짜를
# 다루지 않으므로, 문자열로 읽어 조용히 다른 값을 내느니 ★닫는다★.
# 워크플로에서 날짜를 값으로 쓰려면 인용하면 된다(`"2026-08-06"`).
_TIMESTAMP_RE = _re.compile(r"\A[0-9]{4}-[0-9]{1,2}-[0-9]{1,2}(?:[Tt \t].*)?\Z")


def _typed(text: str):
    """인용 없는 스칼라를 YAML 1.1 규칙으로 해석한다.

    ★PyYAML 과 같은 값을 내야 한다. 시험이 저장소의 모든 워크플로로 대조한다.
    ★맞출 수 없는 표기(날짜)는 흉내내지 않고 닫는다.
    """
    if _TIMESTAMP_RE.match(text):
        raise WorkflowYamlError(WORKFLOW_YAML_UNSUPPORTED)
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    if text in _NULL:
        return None
    if _INT_RE.match(text):
        cleaned = text.replace("_", "")
        try:
            if ":" in cleaned:
                return text  # 60진법 표기는 이 저장소가 쓰지 않는다 — 문자열로 둔다
            return int(cleaned, 0) if cleaned.lower().startswith(("0x", "0b", "-0x", "+0x")) \
                else int(cleaned, 8) if _re.match(r"\A[-+]?0[0-7]+\Z", cleaned) \
                else int(cleaned, 10)
        except ValueError:
            return text
    if _FLOAT_RE.match(text):
        cleaned = text.replace("_", "")
        if "inf" in cleaned.lower() or "nan" in cleaned.lower() or ":" in cleaned:
            return text  # 이 저장소가 쓰지 않는 표기 — 문자열로 둔다
        try:
            return float(cleaned)
        except ValueError:
            return text
    return text


def _read_lines(text: str) -> list[_Line]:
    lines: list[_Line] = []
    for number, raw in enumerate(text.splitlines(), 1):
        if "\t" in raw[: len(raw) - len(raw.lstrip())]:
            raise WorkflowYamlError(WORKFLOW_YAML_MALFORMED, number)
        stripped = _strip_comment(raw)
        if not stripped.strip():
            continue
        lines.append(_Line(number, len(raw) - len(raw.lstrip(" ")), stripped.strip()))
    return lines


class _Parser:
    def __init__(self, text: str) -> None:
        self._raw_lines = text.splitlines()
        self._lines = _read_lines(text)
        self._index = 0

    # ── 커서 ──────────────────────────────────────────────────────────
    def _peek(self) -> _Line | None:
        return self._lines[self._index] if self._index < len(self._lines) else None

    def _next(self) -> _Line:
        line = self._lines[self._index]
        self._index += 1
        return line

    # ── 블록 스칼라 ───────────────────────────────────────────────────
    def _block_scalar(self, marker: str, parent_indent: int, start_line: int) -> str:
        """`|` 이후의 들여쓴 줄을 원문 그대로 모은다(주석 제거 없음)."""
        folded = marker.startswith(">")
        keep = marker.endswith("+")
        strip = marker.endswith("-")

        collected: list[str] = []
        block_indent: int | None = None
        cursor = start_line  # 0-based index into _raw_lines
        while cursor < len(self._raw_lines):
            raw = self._raw_lines[cursor]
            if not raw.strip():
                collected.append("")
                cursor += 1
                continue
            indent = len(raw) - len(raw.lstrip(" "))
            if indent <= parent_indent:
                break
            if block_indent is None:
                block_indent = indent
            if indent < block_indent:
                break
            collected.append(raw[block_indent:])
            cursor += 1

        # 소비한 논리 줄을 커서에서 건너뛴다
        consumed_until = cursor
        while self._index < len(self._lines) and self._lines[self._index].number <= consumed_until:
            self._index += 1

        while collected and not collected[-1].strip():
            if keep:
                break
            collected.pop()
        body = ("\n".join(collected)) if not folded else (" ".join(x for x in collected if x))
        if strip:
            return body
        return body + "\n" if body else ""

    # ── 값 ────────────────────────────────────────────────────────────
    def _value(self, token: str, indent: int, line: _Line):
        token = token.strip()
        if token in _BLOCK_MARKERS:
            return self._block_scalar(token, indent, line.number)
        if token.startswith(("[", "{")):
            return _flow_collection(token, line.number)
        if token:
            return _scalar(token, line.number)
        # 값이 다음 줄부터 온다 — 더 깊은 들여쓰기의 맵 또는 시퀀스
        following = self._peek()
        if following is None or following.indent <= indent:
            return ""
        if following.text.startswith("- "):
            return self._sequence(following.indent)
        return self._mapping(following.indent)

    # ── 시퀀스 ────────────────────────────────────────────────────────
    def _sequence(self, indent: int) -> list:
        items: list = []
        while True:
            line = self._peek()
            if line is None or line.indent < indent or not line.text.startswith("- "):
                if line is not None and line.indent == indent and not line.text.startswith("- "):
                    break
                if line is None or line.indent < indent:
                    break
                if not line.text.startswith("- "):
                    break
            if line.indent != indent:
                break
            self._next()
            body = line.text[2:].strip()
            item_indent = indent + 2
            if ":" in body and not body.startswith(("'", '"')):
                key, _, rest = body.partition(":")
                entry: dict = {}
                entry[_scalar(key, line.number)] = self._value(rest, item_indent, line)
                nested = self._peek()
                if nested is not None and nested.indent >= item_indent:
                    entry.update(self._mapping(nested.indent))
                items.append(entry)
            elif body:
                items.append(_scalar(body, line.number))
            else:
                nested = self._peek()
                if nested is None or nested.indent <= indent:
                    items.append("")
                else:
                    items.append(self._mapping(nested.indent))
        return items

    # ── 맵 ────────────────────────────────────────────────────────────
    def _mapping(self, indent: int) -> dict:
        found: dict = {}
        while True:
            line = self._peek()
            if line is None or line.indent < indent:
                break
            if line.indent > indent:
                raise WorkflowYamlError(WORKFLOW_YAML_MALFORMED, line.number)
            if line.text.startswith("- "):
                break
            self._next()
            if ":" not in line.text:
                raise WorkflowYamlError(WORKFLOW_YAML_MALFORMED, line.number)
            key_token, _, rest = line.text.partition(":")
            key = _scalar(key_token, line.number)
            if key in found:
                raise WorkflowYamlError(WORKFLOW_YAML_MALFORMED, line.number)
            found[key] = self._value(rest, indent, line)
        return found

    def parse(self) -> dict:
        if not self._lines:
            raise WorkflowYamlError(WORKFLOW_YAML_MALFORMED)
        for line in self._lines:
            if line.text.startswith("---") or line.text.startswith("..."):
                raise WorkflowYamlError(WORKFLOW_YAML_UNSUPPORTED, line.number)
        document = self._mapping(self._lines[0].indent)
        if self._index != len(self._lines):
            raise WorkflowYamlError(WORKFLOW_YAML_MALFORMED, self._lines[self._index].number)
        return document


def load_workflow(text: str) -> dict:
    """워크플로 YAML 부분집합을 dict 로 읽는다. 못 읽으면 닫는다."""
    return _Parser(text).parse()


__all__ = [
    "WORKFLOW_YAML_MALFORMED",
    "WORKFLOW_YAML_UNSUPPORTED",
    "WorkflowYamlError",
    "load_workflow",
]
