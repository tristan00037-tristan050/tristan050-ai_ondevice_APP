"""Butler K-IFRS accounting APIs with dependency-light package startup."""

from importlib import import_module
from typing import Any

__all__ = ["classify_df", "build_summary", "validate_report", "generate_report"]

_EXPORT_MODULES = {
    "classify_df": ".classifier",
    "build_summary": ".report",
    "validate_report": ".report",
    "generate_report": ".report",
}


def __getattr__(name: str) -> Any:
    """Load dataframe and report stacks only when their API is requested."""

    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name, __name__), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
