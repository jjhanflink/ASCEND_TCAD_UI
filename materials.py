"""
materials.py — Material database and command formatting for ASCEND TCAD automation.
Handles material alias resolution, thickness formatting, and Victory Process command strings.
"""

from typing import Dict, Any

# Supported deposition model map
DEPOSIT_MODEL_MAP: Dict[str, str] = {
    "Conformal (ALD/CVD)": "CONFORMAL",
    "Anisotropic (Evaporation)": "ANISOTROPIC",
    "Sputter (PVD)": "SPUTTER"
}

# Material Alias Standardization
MATERIAL_ALIASES: Dict[str, str] = {
    "sio2": "SiO2",
    "oxide": "SiO2",
    "silicon dioxide": "SiO2",
    "si3n4": "Si3N4",
    "nitride": "Si3N4",
    "silicon nitride": "Si3N4",
    "aluminum": "Aluminum",
    "al": "Aluminum",
    "copper": "Copper",
    "cu": "Copper",
    "photoresist": "Photoresist",
    "resist": "Photoresist",
    "pr": "Photoresist",
    "gaas": "GaAs",
    "silicon": "Silicon",
    "si": "Silicon"
}

def normalize_material(name: str) -> str:
    """Standardizes material strings for Silvaco Victory Process syntax."""
    clean_name = name.strip().lower()
    return MATERIAL_ALIASES.get(clean_name, name.strip())

def format_deposit_command(material: str, thickness: float, model: str = "CONFORMAL") -> str:
    """
    Formats a valid Victory Process DEPOSIT statement.
    Always includes a deposition model flag (defaults to CONFORMAL) to prevent simulator syntax errors.
    """
    norm_mat = normalize_material(material)
    
    # Map friendly UI names to Silvaco keywords if passed from GUI
    sim_model = DEPOSIT_MODEL_MAP.get(model, model.upper())
    if sim_model not in ["CONFORMAL", "ANISOTROPIC", "SPUTTER"]:
        sim_model = "CONFORMAL"
        
    return f'DEPOSIT MATERIAL="{norm_mat}" THICK={thickness:.2f} {sim_model}'

def format_mask_command(mask_name: str, thickness: float, reverse: bool = True) -> str:
    """Formats a Photoresist MASK step."""
    rev_flag = " REVERSE" if reverse else ""
    return f'MASK "{mask_name}" MATERIAL="resist" THICKNESS={thickness:.2f}{rev_flag}'

def format_strip_command() -> str:
    """Formats a Photoresist STRIP step."""
    return 'STRIP MATERIAL="resist"'
