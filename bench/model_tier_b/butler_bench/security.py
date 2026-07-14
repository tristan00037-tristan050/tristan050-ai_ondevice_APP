"""Security scanning facade.

v2.8 intentionally exposes only the closed-tree scanner.  The old API that
accepted an arbitrary list of files was removed because it could omit unsafe
artifacts while still producing a PASS receipt.
"""

from .artifact_scanner import scan_artifact_tree, scan_bytes_all_encodings

__all__ = ["scan_artifact_tree", "scan_bytes_all_encodings"]
