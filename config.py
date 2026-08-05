"""
config.py — ASCEND TCAD Pipeline
Typed configuration dataclasses for one TCAD simulation run.

Responsibilities:
  - Typed config objects (TCADConfig, DopingConfig, ExtractionWindow,
    LayerConfig, SimulationSettings)
  - SYNTAX validation only: are required fields present, are files where
    they should be, are numbers positive? (call .validate())
  - Engineering sanity checks live in validator.TCADValidator — see that
    module for the "does this make physical sense?" layer.
  - JSON serialization for reproducibility and replay mode.

Usage:
    from config import TCADConfig, DopingConfig, ExtractionWindow, LayerConfig, SimulationSettings
"""

from __future__ import annotations
import json
import re
from dataclasses import dataclass, field
from pathlib import Path


# ── Version ────────────────────────────────────────────────────────────────────
ASCEND_VERSION = "1.1.0"


# ──────────────────────────────────────────────────────────────────────────────
# Sub-configs
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class DopingConfig:
    """Substrate doping parameters."""
    dopant: str = "phosphorus"
    concentration: float = 1e16        # cm^-3

    _VALID_DOPANTS = frozenset({"phosphorus", "boron", "arsenic", "antimony"})

    def __post_init__(self):
        if self.dopant.lower() not in self._VALID_DOPANTS:
            raise ValueError(
                f"Unknown dopant '{self.dopant}'. "
                f"Choose from: {', '.join(sorted(self._VALID_DOPANTS))}"
            )
        if not (1e10 <= self.concentration <= 1e22):
            raise ValueError(
                f"Doping concentration {self.concentration:.2e} cm⁻³ is outside the "
                f"physical range [1e10, 1e22] cm⁻³."
            )


@dataclass
class ExtractionWindow:
    """
    Geometric extraction window for the LAYOUT/GDS slice.
    FROM=x_from, TO=x_to, AT=y_at  (all in µm)
    """
    x_from: float = -3.0
    x_to: float = 3.0
    y_at: float = 0.0

    def validate(self) -> None:
        if self.x_from >= self.x_to:
            raise ValueError(
                f"Extraction window: x_from ({self.x_from} µm) must be "
                f"strictly less than x_to ({self.x_to} µm)."
            )


@dataclass
class LayerConfig:
    """A single process step (deposit, mask, etch, or implant)."""
    material: str       # Canonical name from normalize_material()
    thickness: float    # µm

    def validate(self, index: int) -> None:
        if self.thickness <= 0:
            raise ValueError(
                f"Layer {index} ('{self.material}'): thickness must be > 0, "
                f"got {self.thickness} µm."
            )


@dataclass
class SimulationSettings:
    """
    Victory Process solver / runtime settings.

    Previously hardcoded as  simflags="-P 24 -128"
    Now fully configurable — the pipeline is no longer tied to one server's
    core count or memory configuration.

    notation controls doping number formatting:
      "scientific" → 2.000e+19   (more readable, default)
      "compact"    → 2e19        (some older Silvaco parsers prefer this)
    """
    num_threads: int = 24
    memory_limit_mb: int = 128
    extra_simflags: str = ""
    notation: str = "scientific"       # "scientific" | "compact"

    _VALID_NOTATIONS = frozenset({"scientific", "compact"})

    def validate(self) -> None:
        if self.num_threads < 1:
            raise ValueError(f"num_threads must be ≥ 1, got {self.num_threads}.")
        if self.num_threads > 256:
            raise ValueError(
                f"num_threads={self.num_threads} looks too high for any real server. "
                "Double-check the core count."
            )
        if self.memory_limit_mb < 1:
            raise ValueError(f"memory_limit_mb must be ≥ 1, got {self.memory_limit_mb}.")
        if self.notation not in self._VALID_NOTATIONS:
            raise ValueError(
                f"notation must be one of {sorted(self._VALID_NOTATIONS)}, "
                f"got '{self.notation}'."
            )

    def build_simflags(self) -> str:
        """Return the complete simflags string for the go statement."""
        flags = f"-P {self.num_threads} -{self.memory_limit_mb}"
        if self.extra_simflags.strip():
            flags += f" {self.extra_simflags.strip()}"
        return flags

    def format_number(self, value: float) -> str:
        """
        Format a float for use in a Victory Process command.

        "scientific" → f"{value:.3e}"   e.g. 2.000e+19
        "compact"    → shortest form    e.g. 2e19

        Some older Silvaco versions trip over the padded exponent in standard
        Python scientific notation. Use "compact" if you see INIT parser errors.
        """
        if self.notation == "compact":
            s = f"{value:e}"
            mantissa, exp = s.split("e")
            mantissa = mantissa.rstrip("0").rstrip(".")
            exp_sign = "-" if exp[0] == "-" else ""
            exp_digits = exp[1:].lstrip("0") or "0"
            return f"{mantissa}e{exp_sign}{exp_digits}"
        return f"{value:.3e}"


# ──────────────────────────────────────────────────────────────────────────────
# Root config
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class TCADConfig:
    """
    Complete configuration for one TCAD simulation run.

    Two GDS paths — always separate:
      gds_file_local  : validated locally (must exist on this machine)
      gds_file_server : embedded in the .in script (path on the Linux server)

    This prevents the classic bug where a Windows path like
    C:\\Users\\me\\project\\mask.gds ends up inside the DeckBuild script and
    crashes immediately on the server.
    """

    # ── Identity ───────────────────────────────────────────────────────────────
    project_name: str

    # ── GDS paths ──────────────────────────────────────────────────────────────
    gds_file_local: str
    gds_file_server: str

    # ── Substrate ──────────────────────────────────────────────────────────────
    substrate_material: str = "Silicon"
    substrate_thickness: float = 8.0    # µm

    # ── Electrical ─────────────────────────────────────────────────────────────
    doping: DopingConfig = field(default_factory=DopingConfig)

    # ── Simulation geometry ────────────────────────────────────────────────────
    extraction: ExtractionWindow = field(default_factory=ExtractionWindow)
    resolution: float = 1.0             # µm
    cell_name: str = "TOP"

    # ── Process stack ──────────────────────────────────────────────────────────
    layers: list[LayerConfig] = field(default_factory=list)

    # ── Solver settings ────────────────────────────────────────────────────────
    simulation: SimulationSettings = field(default_factory=SimulationSettings)

    # ── Output ─────────────────────────────────────────────────────────────────
    output_dir: str = "output"

    # ──────────────────────────────────────────────────────────────────────────
    # SYNTAX validation — "is this config well-formed?"
    # Engineering sanity checks ("does this make physical sense?") are
    # handled by validator.TCADValidator, which runs after this.
    # ──────────────────────────────────────────────────────────────────────────

    def validate(self) -> None:
        """
        Syntax-level pre-flight check. Raises on malformed input.
        Call this before TCADValidator.
        """
        self._validate_project_name()
        self._validate_gds()
        self._validate_substrate()
        self.extraction.validate()
        self._validate_resolution()
        self.simulation.validate()
        for i, layer in enumerate(self.layers, start=1):
            layer.validate(i)

    def _validate_project_name(self) -> None:
        name = self.project_name.strip()
        if not name:
            raise ValueError("project_name cannot be empty.")
        if not re.match(r"^[A-Za-z0-9_\-]+$", name):
            raise ValueError(
                f"project_name '{name}' contains invalid characters. "
                "Use only letters, digits, underscores, and hyphens."
            )

    def _validate_gds(self) -> None:
        local = Path(self.gds_file_local)
        if not local.exists():
            raise FileNotFoundError(
                f"GDS file not found locally: '{self.gds_file_local}'\n"
                "  • Check the path and your working directory.\n"
                "  • The file must exist locally before validation."
            )
        if local.suffix.lower() != ".gds":
            raise ValueError(
                f"Expected a .gds file, got: '{local.name}'. "
                "KLayout exports should use the .gds extension."
            )
        if not self.gds_file_server.strip():
            raise ValueError(
                "gds_file_server cannot be empty. "
                "Enter the path or filename as it will appear on the Linux server."
            )

    def _validate_substrate(self) -> None:
        if self.substrate_thickness <= 0:
            raise ValueError(
                f"substrate_thickness must be > 0, got {self.substrate_thickness} µm."
            )

    def _validate_resolution(self) -> None:
        if self.resolution <= 0:
            raise ValueError(f"resolution must be > 0, got {self.resolution}.")

    # ──────────────────────────────────────────────────────────────────────────
    # Serialization
    # ──────────────────────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        """Serialize to a plain JSON-compatible dict."""
        return {
            "_ascend_version": ASCEND_VERSION,
            "project_name": self.project_name,
            "gds_file_local": self.gds_file_local,
            "gds_file_server": self.gds_file_server,
            "substrate_material": self.substrate_material,
            "substrate_thickness": self.substrate_thickness,
            "doping": {
                "dopant": self.doping.dopant,
                "concentration": self.doping.concentration,
            },
            "extraction": {
                "x_from": self.extraction.x_from,
                "x_to": self.extraction.x_to,
                "y_at": self.extraction.y_at,
            },
            "cell_name": self.cell_name,
            "resolution": self.resolution,
            "layers": [
                {"material": l.material, "thickness": l.thickness}
                for l in self.layers
            ],
            "simulation": {
                "num_threads": self.simulation.num_threads,
                "memory_limit_mb": self.simulation.memory_limit_mb,
                "extra_simflags": self.simulation.extra_simflags,
                "notation": self.simulation.notation,
            },
            "output_dir": self.output_dir,
        }

    def save_json(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def from_dict(cls, d: dict) -> "TCADConfig":
        """
        Reconstruct from a dict. Material aliases are normalized so that configs
        saved with shorthand names ("oxide", "poly") round-trip correctly.
        """
        from materials import normalize_material

        def _norm_layer(l: dict) -> LayerConfig:
            try:
                canonical = normalize_material(l["material"])
            except ValueError:
                canonical = l["material"]   # leave as-is; validate() will catch it
            return LayerConfig(material=canonical, thickness=float(l["thickness"]))

        sim_d = d.get("simulation", {})
        return cls(
            project_name=d["project_name"],
            gds_file_local=d["gds_file_local"],
            gds_file_server=d["gds_file_server"],
            substrate_material=d.get("substrate_material", "Silicon"),
            substrate_thickness=float(d["substrate_thickness"]),
            doping=DopingConfig(
                dopant=d["doping"]["dopant"],
                concentration=float(d["doping"]["concentration"]),
            ),
            extraction=ExtractionWindow(
                x_from=float(d["extraction"]["x_from"]),
                x_to=float(d["extraction"]["x_to"]),
                y_at=float(d["extraction"]["y_at"]),
            ),
            cell_name=d.get("cell_name", "TOP"),
            resolution=float(d.get("resolution", 1.0)),
            layers=[_norm_layer(l) for l in d.get("layers", [])],
            simulation=SimulationSettings(
                num_threads=int(sim_d.get("num_threads", 24)),
                memory_limit_mb=int(sim_d.get("memory_limit_mb", 128)),
                extra_simflags=sim_d.get("extra_simflags", ""),
                notation=sim_d.get("notation", "scientific"),
            ),
            output_dir=d.get("output_dir", "output"),
        )

    @classmethod
    def from_json(cls, path: Path) -> "TCADConfig":
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))
