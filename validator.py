"""
validator.py — ASCEND TCAD Pipeline
Semantic (engineering sanity) validation layer.

The pipeline has two validation stages — this is the second one:

  Stage 1 — config.TCADConfig.validate()
    Syntax validation: required fields present, files exist, numbers positive.
    Answers: "Is this config well-formed?"

  Stage 2 — validator.TCADValidator (this module)
    Semantic validation: do the values make physical / engineering sense?
    Answers: "Will this actually produce a meaningful simulation?"

The design mirrors a compiler: parsing/type-checking first, then semantic
analysis. Separating these means config.py stays simple and this module can
grow into a full process-engineering rule checker without touching config.py.

TCADValidator never raises — it returns a list of ValidationIssue objects.
Issues with severity="error" halt the pipeline; "warning" issues are shown
to the user and recorded in summary.txt but don't block the run.

Usage:
    from validator import TCADValidator

    issues = TCADValidator(config).validate()
    errors = [i for i in issues if i.severity == "error"]
    warnings = [i for i in issues if i.severity == "warning"]
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Literal

from config import TCADConfig
import gds_tools


# ──────────────────────────────────────────────────────────────────────────────
# Issue model
# ──────────────────────────────────────────────────────────────────────────────

Severity = Literal["error", "warning", "info"]

@dataclass
class ValidationIssue:
    severity: Severity
    code: str        # Short machine-readable ID, e.g. "RESOLUTION_RANGE"
    message: str

    def __str__(self) -> str:
        markers = {"error": "✗", "warning": "⚠", "info": "ℹ"}
        return f"{markers[self.severity]}  [{self.code}] {self.message}"


# ──────────────────────────────────────────────────────────────────────────────
# Engineering sanity limits (all in µm unless noted)
# Tuning these is straightforward — they're all in one place.
# ──────────────────────────────────────────────────────────────────────────────

RES_MIN          = 0.001     # µm — finer than this is rarely useful in VP
RES_MAX          = 10.0      # µm — coarser than this gives very low resolution

SUB_MIN          = 0.01      # µm
SUB_MAX          = 1000.0    # µm

LAYER_MIN        = 0.0001    # µm
LAYER_MAX        = 200.0     # µm

WIN_MIN_SPAN     = 0.01      # µm — extraction window must be at least this wide
WIN_MAX_SPAN     = 5000.0    # µm — catching obvious unit mistakes (nm entered as µm)

MIN_MESH_POINTS  = 2         # window / resolution — too few = under-resolved
MAX_MESH_POINTS  = 50_000    # window / resolution — too many = very slow sim


# ──────────────────────────────────────────────────────────────────────────────
# Validator
# ──────────────────────────────────────────────────────────────────────────────

class TCADValidator:
    """
    Semantic validation pass for a TCADConfig.

    Checks:
      - Resolution within realistic TCAD range
      - Substrate thickness within realistic range
      - Extraction window span and mesh density
      - Per-layer thickness within realistic range
      - Duplicate consecutive layer steps (likely a mistake)
      - Trailing mask step with no following deposit
      - SimulationSettings consistency
      - GDS cell existence (optional / best-effort)
    """

    def __init__(self, config: TCADConfig):
        self.cfg = config

    def validate(self) -> list[ValidationIssue]:
        """Run all checks and return the combined issue list."""
        issues: list[ValidationIssue] = []
        issues += self._check_resolution()
        issues += self._check_substrate()
        issues += self._check_extraction_window()
        issues += self._check_process_stack()
        issues += self._check_simulation_settings()
        issues += self._check_gds_cell()
        return issues

    # ── Individual checks ─────────────────────────────────────────────────────

    def _check_resolution(self) -> list[ValidationIssue]:
        r = self.cfg.resolution
        if not (RES_MIN <= r <= RES_MAX):
            return [ValidationIssue(
                "error", "RESOLUTION_RANGE",
                f"Mesh resolution {r} µm is outside the realistic range "
                f"[{RES_MIN}, {RES_MAX}] µm. "
                f"Typical Victory Process meshes use 0.1–1 µm."
            )]
        return []

    def _check_substrate(self) -> list[ValidationIssue]:
        t = self.cfg.substrate_thickness
        issues = []
        if not (SUB_MIN <= t <= SUB_MAX):
            issues.append(ValidationIssue(
                "error", "SUBSTRATE_THICKNESS_RANGE",
                f"Substrate thickness {t} µm is outside the realistic range "
                f"[{SUB_MIN}, {SUB_MAX}] µm. "
                f"Did you use nm or mm instead of µm?"
            ))
        elif t > 50:
            issues.append(ValidationIssue(
                "warning", "SUBSTRATE_THICKNESS_LARGE",
                f"Substrate thickness {t} µm is larger than typical simulated "
                f"regions (usually 1–20 µm). This may increase simulation time "
                f"significantly. Confirm this is intentional."
            ))
        return issues

    def _check_extraction_window(self) -> list[ValidationIssue]:
        issues = []
        ext = self.cfg.extraction
        span = ext.x_to - ext.x_from

        if span < WIN_MIN_SPAN:
            issues.append(ValidationIssue(
                "error", "WINDOW_TOO_NARROW",
                f"Extraction window span ({span} µm) is below the minimum "
                f"useful width of {WIN_MIN_SPAN} µm."
            ))
        elif span > WIN_MAX_SPAN:
            issues.append(ValidationIssue(
                "error", "WINDOW_TOO_WIDE",
                f"Extraction window span ({span} µm) exceeds {WIN_MAX_SPAN} µm. "
                f"This often means nm values were entered as µm."
            ))

        if self.cfg.resolution > 0 and WIN_MIN_SPAN <= span <= WIN_MAX_SPAN:
            points = span / self.cfg.resolution
            if points < MIN_MESH_POINTS:
                issues.append(ValidationIssue(
                    "warning", "WINDOW_UNDER_RESOLVED",
                    f"Window ({span} µm) / resolution ({self.cfg.resolution} µm) "
                    f"= only {points:.1f} mesh points. "
                    f"Consider a finer resolution or wider window."
                ))
            elif points > MAX_MESH_POINTS:
                issues.append(ValidationIssue(
                    "warning", "WINDOW_OVER_RESOLVED",
                    f"Window spans ~{points:,.0f} mesh points — this will "
                    f"produce a very large mesh and a slow simulation."
                ))

        return issues

    def _check_process_stack(self) -> list[ValidationIssue]:
        issues = []
        layers = self.cfg.layers
        from materials import get_material

        for i, layer in enumerate(layers, start=1):
            if not (LAYER_MIN <= layer.thickness <= LAYER_MAX):
                issues.append(ValidationIssue(
                    "error", "LAYER_THICKNESS_RANGE",
                    f"Layer {i} ('{layer.material}'): thickness "
                    f"{layer.thickness} µm is outside the realistic range "
                    f"[{LAYER_MIN}, {LAYER_MAX}] µm."
                ))

        # Duplicate consecutive layers
        for i in range(1, len(layers)):
            if layers[i - 1].material == layers[i].material:
                issues.append(ValidationIssue(
                    "warning", "DUPLICATE_CONSECUTIVE_LAYER",
                    f"Steps {i} and {i + 1} both use '{layers[i].material}'. "
                    f"Consider combining them into one step unless separate "
                    f"deposition cycles are intentional."
                ))

        # Mask step with nothing deposited after it
        for i, layer in enumerate(layers, start=1):
            try:
                mat = get_material(layer.material)
            except ValueError:
                continue
            if mat.process_mode == "mask" and i == len(layers):
                issues.append(ValidationIssue(
                    "warning", "TRAILING_MASK_STEP",
                    f"Step {i} ('{layer.material}') is a mask/resist step "
                    f"with no deposit step after it. Verify this is intended."
                ))

        return issues

    def _check_simulation_settings(self) -> list[ValidationIssue]:
        try:
            self.cfg.simulation.validate()
        except ValueError as e:
            return [ValidationIssue("error", "SIMULATION_SETTINGS", str(e))]
        return []

    def _check_gds_cell(self) -> list[ValidationIssue]:
        """
        Best-effort GDS cell check. Gracefully skipped if no library available.
        Never blocks the pipeline regardless of result.
        """
        result = gds_tools.cell_exists(self.cfg.gds_file_local, self.cfg.cell_name)
        if result is None:
            return [ValidationIssue(
                "info", "GDS_CELL_SKIPPED",
                "GDS cell validation skipped — no gdspy or klayout Python API "
                "available. Manually confirm the CELL= name before running on "
                "the server. (Install gdspy with:  pip install gdspy)"
            )]
        if result is False:
            return [ValidationIssue(
                "warning", "GDS_CELL_NOT_FOUND",
                f"Cell '{self.cfg.cell_name}' was NOT found in "
                f"'{self.cfg.gds_file_local}'. Check the CELL= parameter "
                f"against your actual top cell name in KLayout."
            )]
        return [ValidationIssue(
            "info", "GDS_CELL_VERIFIED",
            f"Confirmed: cell '{self.cfg.cell_name}' exists in the GDS file."
        )]
