"""
materials.py — ASCEND TCAD Pipeline
Material database with canonical names, Silvaco Victory Process identifiers,
and robust user-input normalization via alias resolution.

Key design: process_mode lives on the Material object, not in generator.py.
This means the generator never contains material-specific if/else logic —
it dispatches on process_mode. Adding a new process behavior (e.g. "etch",
"implant") only requires a new entry here and one new branch in the generator.

Usage:
    from materials import normalize_material, get_material, MATERIAL_DB
"""

from dataclasses import dataclass
from typing import Optional


# ──────────────────────────────────────────────────────────────────────────────
# Data model
# ──────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Material:
    """
    Represents a single process material.

    process_mode drives which Victory Process command the generator emits:
      "deposit" → DEPOSIT MATERIAL=... THICK=...
      "mask"    → MASK "L#..." MATERIAL=... THICKNESS=... REVERSE
      "etch"    → ETCH MATERIAL=... THICK=...   (future)
      "implant" → IMPLANT ...                   (future)

    The generator dispatches on this field. No material names are ever
    hardcoded inside generator.py.
    """
    name: str                          # Canonical display name
    mat_type: str                      # "semiconductor" | "insulator" | "metal" | "organic"
    silvaco_name: str                  # Exact name for Victory Process commands
    process_mode: str = "deposit"      # "deposit" | "mask" | "etch" | "implant"
    default_doping: Optional[float] = None  # cm^-3, for semiconductor substrates

    _VALID_MODES = frozenset({"deposit", "mask", "etch", "implant"})

    def __post_init__(self):
        if self.process_mode not in self._VALID_MODES:
            raise ValueError(
                f"Material '{self.name}': invalid process_mode "
                f"'{self.process_mode}'. Must be one of {sorted(self._VALID_MODES)}."
            )

    def is_resist(self) -> bool:
        """Convenience alias for process_mode == 'mask'. Kept for readability."""
        return self.process_mode == "mask"


# ──────────────────────────────────────────────────────────────────────────────
# Material database
# silvaco_name must exactly match what Victory Process expects.
# ──────────────────────────────────────────────────────────────────────────────

MATERIAL_DB: dict[str, Material] = {
    "Silicon":         Material("Silicon",         "semiconductor", "Silicon",      "deposit", 1e16),
    "SiO2":            Material("SiO2",            "insulator",     "SiO2",         "deposit"),
    "Photoresist":     Material("Photoresist",     "organic",       "resist",       "mask"),
    "Aluminum":        Material("Aluminum",        "metal",         "Aluminum",     "deposit"),
    "Nickel":          Material("Nickel",          "metal",         "Nickel",       "deposit"),
    "Copper":          Material("Copper",          "metal",         "Copper",       "deposit"),
    "Polysilicon":     Material("Polysilicon",     "semiconductor", "Polysilicon",  "deposit"),
    "Silicon Nitride": Material("Silicon Nitride", "insulator",     "Si3N4",        "deposit"),
    "TiN":             Material("TiN",             "metal",         "TiN",          "deposit"),
    "Titanium":        Material("Titanium",        "metal",         "Titanium",     "deposit"),
    "Gold":            Material("Gold",            "metal",         "Gold",         "deposit"),
    "Tungsten":        Material("Tungsten",        "metal",         "Tungsten",     "deposit"),
    "GaAs":            Material("GaAs",            "semiconductor", "GaAs",         "deposit"),
}

# Alias map: lowercase alias → canonical name
# Catches abbreviations, typos, and naming variants.
_ALIASES: dict[str, str] = {
    # Silicon
    "si": "Silicon", "silicon": "Silicon", "bulk silicon": "Silicon",
    # SiO2
    "sio2": "SiO2", "oxide": "SiO2", "silicon dioxide": "SiO2",
    "thermal oxide": "SiO2", "gate oxide": "SiO2", "field oxide": "SiO2",
    # Photoresist
    "photoresist": "Photoresist", "resist": "Photoresist", "pr": "Photoresist",
    "photo resist": "Photoresist", "photo-resist": "Photoresist",
    # Aluminum
    "al": "Aluminum", "aluminum": "Aluminum", "aluminium": "Aluminum",
    # Nickel
    "ni": "Nickel", "nickel": "Nickel",
    # Copper
    "cu": "Copper", "copper": "Copper",
    # Polysilicon
    "poly": "Polysilicon", "polysilicon": "Polysilicon",
    "poly-si": "Polysilicon", "poly si": "Polysilicon", "polysi": "Polysilicon",
    # Silicon Nitride
    "si3n4": "Silicon Nitride", "sin": "Silicon Nitride",
    "silicon nitride": "Silicon Nitride", "nitride": "Silicon Nitride",
    # TiN
    "tin": "TiN", "titanium nitride": "TiN",
    # Titanium
    "ti": "Titanium", "titanium": "Titanium",
    # Gold
    "au": "Gold", "gold": "Gold",
    # Tungsten
    "w": "Tungsten", "tungsten": "Tungsten",
    # GaAs
    "gaas": "GaAs", "gallium arsenide": "GaAs",
}


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

def normalize_material(name: str) -> str:
    """
    Convert a user-supplied material string to its canonical name.
    Case-insensitive. Resolves common aliases.

    Examples:
        normalize_material("nickel")       → "Nickel"
        normalize_material("SiO2")         → "SiO2"
        normalize_material("poly")         → "Polysilicon"
        normalize_material("photoresist")  → "Photoresist"

    Raises:
        ValueError: if the material cannot be recognized.
    """
    lookup = name.strip().lower()

    if lookup in _ALIASES:
        return _ALIASES[lookup]

    for canonical in MATERIAL_DB:
        if canonical.lower() == lookup:
            return canonical

    available = ", ".join(sorted(MATERIAL_DB.keys()))
    raise ValueError(
        f"Unrecognized material: '{name}'.\n"
        f"  Known materials : {available}\n"
        f"  Common aliases  : poly, resist, oxide, nitride, si, al, ni, cu, ti …"
    )


def get_material(name: str) -> Material:
    """
    Normalize name and return the corresponding Material object.
    Raises ValueError if unrecognized.
    """
    return MATERIAL_DB[normalize_material(name)]
