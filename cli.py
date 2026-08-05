"""
cli.py — ASCEND TCAD Pipeline
Interactive CLI that collects user input and returns a TCADConfig.

This module only collects input — it does not validate, generate, or write
any files. All prompts retry on invalid input with a clear error message.

Usage:
    from cli import collect_config
    config = collect_config()
"""

import sys
from pathlib import Path

from config import TCADConfig, DopingConfig, ExtractionWindow, LayerConfig, SimulationSettings
from materials import normalize_material, MATERIAL_DB


# ──────────────────────────────────────────────────────────────────────────────
# Primitive input helpers
# ──────────────────────────────────────────────────────────────────────────────

def _ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        raw = input(f"  {prompt}{suffix}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n\n  Aborted.")
        sys.exit(0)
    return raw or default


def _ask_float(prompt: str, default: float) -> float:
    while True:
        raw = _ask(prompt, str(default))
        try:
            return float(raw)
        except ValueError:
            print(f"  ✗  '{raw}' is not a valid number. Try again.")


def _ask_int(prompt: str, default: int) -> int:
    while True:
        raw = _ask(prompt, str(default))
        try:
            return int(raw)
        except ValueError:
            print(f"  ✗  '{raw}' is not a valid integer. Try again.")


def _ask_bool(prompt: str, default: bool = False) -> bool:
    hint = "Y/n" if default else "y/N"
    raw = _ask(f"{prompt} ({hint})", "").lower()
    if not raw:
        return default
    return raw in ("y", "yes", "1", "true")


def _ask_material(prompt: str, step_num: int) -> str:
    while True:
        raw = _ask(f"Step {step_num} — {prompt}")
        if not raw:
            print("  ✗  Material name cannot be empty.")
            continue
        try:
            canonical = normalize_material(raw)
            print(f"       → Recognized as: {canonical}")
            return canonical
        except ValueError as e:
            print(f"  ✗  {str(e).splitlines()[0]}")
            print(f"     Common aliases: poly, resist, oxide, nitride, al, ni, cu")


# ──────────────────────────────────────────────────────────────────────────────
# Section collectors
# ──────────────────────────────────────────────────────────────────────────────

def _collect_project() -> tuple[str, str]:
    print("  ─── Project ────────────────────────────────────────────")
    project_name = _ask("Project name", "MyDevice")
    output_dir   = _ask("Output directory", "output")
    return project_name, output_dir


def _collect_gds() -> tuple[str, str]:
    print()
    print("  ─── GDS Layout File ────────────────────────────────────")
    print("  You will be asked for two paths:")
    print("  • Local path  — where the file is on this computer (for validation)")
    print("  • Server path — what goes inside the .in script (used by DeckBuild)")
    print()

    gds_local = _ask("Local GDS file path", "Test_Mask.gds")
    local_p = Path(gds_local)

    if local_p.exists():
        print(f"  ✓  Found locally: {local_p.resolve()}")
    else:
        print(f"  ⚠  File not found at '{gds_local}'. Make sure it exists before")
        print(f"     running the pipeline — validation will fail otherwise.")

    gds_server = _ask(
        "Server-side GDS path (goes in .in script)",
        local_p.name,
    )
    return gds_local, gds_server


def _collect_substrate() -> tuple[float, DopingConfig]:
    print()
    print("  ─── Substrate ──────────────────────────────────────────")
    thickness = _ask_float("Thickness (µm)", 8.0)

    while True:
        conc_str = _ask("Doping concentration (cm⁻³)", "2e19")
        try:
            concentration = float(conc_str)
            break
        except ValueError:
            print(f"  ✗  '{conc_str}' is not a valid number.")

    dopant = _ask("Dopant type  (phosphorus / boron / arsenic / antimony)", "phosphorus")

    while True:
        try:
            doping = DopingConfig(dopant=dopant.lower().strip(), concentration=concentration)
            break
        except ValueError as e:
            print(f"  ✗  {e}")
            dopant = _ask("Dopant type", "phosphorus")

    return thickness, doping


def _collect_extraction() -> tuple[ExtractionWindow, float, str]:
    print()
    print("  ─── GDS Extraction Window ──────────────────────────────")
    x_from     = _ask_float("FROM x (µm)", -3.0)
    x_to       = _ask_float("TO x   (µm)",  3.0)
    y_at       = _ask_float("AT y   (µm)",  0.0)
    resolution = _ask_float("Mesh resolution (µm)", 1.0)
    cell_name  = _ask("GDS top cell name", "TOP")
    return ExtractionWindow(x_from=x_from, x_to=x_to, y_at=y_at), resolution, cell_name


def _collect_layers() -> list[LayerConfig]:
    print()
    print("  ─── Process Stack ──────────────────────────────────────")
    available = ", ".join(sorted(MATERIAL_DB.keys()))
    print(f"  Available materials: {available}")
    print()

    layers: list[LayerConfig] = []
    step = 2  # Step 1 is always the INIT substrate

    while True:
        if not _ask_bool(f"  Add process step {step}?", default=False):
            break
        material  = _ask_material("Material name", step)
        thickness = _ask_float(f"    Thickness (µm)", 1.0)
        layers.append(LayerConfig(material=material, thickness=thickness))
        step += 1
        print()

    return layers


def _collect_simulation() -> SimulationSettings:
    print()
    print("  ─── Simulation Settings ────────────────────────────────")
    print("  (Press Enter to accept defaults — these match the university server)")
    threads  = _ask_int("CPU threads (-P flag)", 24)
    memory   = _ask_int("Memory limit MB", 128)
    notation = _ask("Number notation  (scientific / compact)", "scientific")
    while notation not in ("scientific", "compact"):
        print("  ✗  Enter 'scientific' or 'compact'.")
        notation = _ask("Number notation", "scientific")
    return SimulationSettings(
        num_threads=threads,
        memory_limit_mb=memory,
        notation=notation,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Public entry point
# ──────────────────────────────────────────────────────────────────────────────

def collect_config() -> TCADConfig:
    """
    Run the full interactive CLI and return a populated TCADConfig.
    Does NOT call validate() — the pipeline (main.py) handles that.
    """
    from config import ASCEND_VERSION
    W = 62
    print()
    print("  " + "═" * W)
    print("  ASCEND — TCAD Fabrication Automation Tool")
    print(f"  Silvaco Victory Process Script Generator  v{ASCEND_VERSION}")
    print("  " + "═" * W)
    print()

    project_name, output_dir        = _collect_project()
    gds_local, gds_server           = _collect_gds()
    substrate_thickness, doping     = _collect_substrate()
    extraction, resolution, cell    = _collect_extraction()
    layers                          = _collect_layers()
    simulation                      = _collect_simulation()

    return TCADConfig(
        project_name=project_name,
        gds_file_local=gds_local,
        gds_file_server=gds_server,
        substrate_material="Silicon",
        substrate_thickness=substrate_thickness,
        doping=doping,
        extraction=extraction,
        cell_name=cell,
        resolution=resolution,
        layers=layers,
        simulation=simulation,
        output_dir=output_dir,
    )
