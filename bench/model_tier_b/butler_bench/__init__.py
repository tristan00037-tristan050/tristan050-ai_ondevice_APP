"""Butler model-tier B benchmark harness.

The package is deliberately fail-closed.  It never supplies production SLOs,
model identities, fixtures, egress evidence, or product entrypoints by default.
"""

from .errors import ExitCode, FailClass, GateError

__all__ = ["ExitCode", "FailClass", "GateError"]
__version__ = "2.8.0"
