from __future__ import annotations

import ast
from pathlib import Path

from .errors import ExitCode, FailClass, GateError


def assert_offline_verifier_independent(path: Path, *, producer_prefix: str = "butler_bench") -> None:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=path.name)
    except (OSError, UnicodeError, SyntaxError):
        raise GateError(FailClass.INDEPENDENT_VERIFY, "VERIFIER_SOURCE_PARSE", exit_code=ExitCode.EVIDENCE) from None
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        else:
            continue
        if any(name == producer_prefix or name.startswith(producer_prefix + ".") for name in names):
            raise GateError(FailClass.INDEPENDENT_VERIFY, "PRODUCER_IMPORT_IN_VERIFIER", exit_code=ExitCode.EVIDENCE)
