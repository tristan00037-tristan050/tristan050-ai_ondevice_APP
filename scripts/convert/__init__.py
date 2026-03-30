"""Butler AI ONNX/MNN conversion pipeline package."""

from __future__ import annotations

__all__ = [
    "EXIT_PASS",
    "EXIT_FAIL",
    "EXIT_STRUCTURE",
    "StructureOrInputError",
    "ConversionStageError",
]

EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_STRUCTURE = 2


class StructureOrInputError(RuntimeError):
    """Raised when an input, dependency, or tool is missing."""


class ConversionStageError(RuntimeError):
    """Raised when a conversion stage runs but does not complete successfully."""
