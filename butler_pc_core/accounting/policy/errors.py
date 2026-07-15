from __future__ import annotations


class PolicyLoadError(RuntimeError):
    """Stable, raw-data-free failure contract for accounting policy loading."""

    def __init__(self, fail_class: str, detail_id: str):
        self.fail_class = fail_class
        self.detail_id = detail_id
        super().__init__(f"{fail_class}:{detail_id}")


def fail(fail_class: str, detail_id: str) -> "None":
    raise PolicyLoadError(fail_class, detail_id)
