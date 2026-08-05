"""
gds_tools.py — ASCEND TCAD Pipeline
Optional, best-effort GDS file inspection.

Neither gdspy nor the KLayout Python API is a hard dependency of ASCEND.
If neither is importable, cell_exists() returns None ("unknown") so the
pipeline is never blocked — it just logs that the check was skipped.

Supported backends (tried in order):
  1. gdspy      — lightweight pure-Python GDS library (pip install gdspy)
  2. klayout    — KLayout's Python bindings     (pip install klayout)
"""

from __future__ import annotations


def _try_gdspy(gds_path: str, cell_name: str) -> bool | None:
    try:
        import gdspy                                          # type: ignore
    except ImportError:
        return None
    try:
        lib = gdspy.GdsLibrary(infile=gds_path)
        return cell_name in lib.cells
    except Exception:
        return None


def _try_klayout(gds_path: str, cell_name: str) -> bool | None:
    try:
        import klayout.db as kdb                              # type: ignore
    except ImportError:
        return None
    try:
        layout = kdb.Layout()
        layout.read(gds_path)
        return layout.cell(cell_name) is not None
    except Exception:
        return None


def cell_exists(gds_path: str, cell_name: str) -> bool | None:
    """
    Best-effort check: does `cell_name` exist in the GDS file?

    Returns:
        True   — cell confirmed present
        False  — cell confirmed absent (check CELL= in your .in script)
        None   — could not determine (no library available, or read error)
    """
    for backend in (_try_gdspy, _try_klayout):
        result = backend(gds_path, cell_name)
        if result is not None:
            return result
    return None
