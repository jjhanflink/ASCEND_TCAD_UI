"""
run_manager.py — ASCEND TCAD Pipeline
Manages structured output artifacts for each simulation run.

Responsibilities:
  - Create a unique, timestamped run directory
  - Set up dual (file + console) logging
  - Write the human-readable summary.txt (research-grade)
  - Log system metadata for reproducibility

Output layout per run:
    output/
    └── <project>_<YYYY-MM-DD_HHmmss>/
        ├── <project>.in     Victory Process script
        ├── config.json      Reproducible machine-readable config
        ├── summary.txt      Human-readable run record
        └── metadata.log     Detailed timestamped log
"""

import logging
import platform
import sys
from datetime import datetime
from pathlib import Path

from config import ASCEND_VERSION


def create_run_dir(base_output: str, project_name: str) -> Path:
    """
    Create a unique timestamped directory for this run's artifacts.
    Example: output/MyDevice_2024-01-15_143022/
    """
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    run_dir = Path(base_output) / f"{project_name}_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def setup_logger(run_dir: Path, project_name: str) -> logging.Logger:
    """
    Configure a named logger with:
      - metadata.log : DEBUG level, full timestamps (for reproducibility)
      - console      : INFO level, clean readable output
    """
    logger = logging.getLogger(f"ascend.{project_name}")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    fh = logging.FileHandler(run_dir / "metadata.log", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s  [%(levelname)-8s]  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("    %(message)s"))

    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger


def log_system_info(logger: logging.Logger) -> None:
    """Log environment metadata into metadata.log."""
    logger.debug("─" * 50)
    logger.debug("ASCEND Version : %s", ASCEND_VERSION)
    logger.debug("System         : %s %s", platform.system(), platform.release())
    logger.debug("Machine        : %s", platform.machine())
    logger.debug("Python         : %s", sys.version.replace("\n", " "))
    logger.debug("CWD            : %s", Path.cwd())
    logger.debug("─" * 50)


def write_summary(
    run_dir: Path,
    config_dict: dict,
    script_filename: str,
    validation_issues: list | None = None,
) -> None:
    """
    Write a professional research-grade run summary to summary.txt.

    Includes: project info, GDS paths, substrate, extraction window,
    process stack, simulation settings, validation status, deployment
    instructions, and software version.
    """
    cfg = config_dict
    dop = cfg["doping"]
    ext = cfg["extraction"]
    sim = cfg.get("simulation", {})
    layers = cfg.get("layers", [])
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    W = 62

    def sec(title: str) -> str:
        pad = max(0, W - len(title) - 6)
        return f"\n  ── {title} {'─' * pad}"

    # ── Validation status ────────────────────────────────────────────────────
    if validation_issues is None:
        val_status = "Not run"
        val_lines = []
    else:
        from validator import ValidationIssue
        errors   = [i for i in validation_issues if i.severity == "error"]
        warnings = [i for i in validation_issues if i.severity == "warning"]
        infos    = [i for i in validation_issues if i.severity == "info"]
        if errors:
            val_status = f"FAILED  ({len(errors)} error(s))"
        elif warnings:
            val_status = f"Passed with warnings  ({len(warnings)} warning(s))"
        else:
            val_status = "Passed"
        val_lines = [str(i) for i in (errors + warnings + infos)]

    # ── Assemble summary ─────────────────────────────────────────────────────
    lines = [
        "=" * W,
        "  ASCEND — TCAD Fabrication Automation",
        "  Silvaco Victory Process Script Generator",
        f"  Version  : {ASCEND_VERSION}",
        "=" * W,
        "",
        f"  Project      : {cfg['project_name']}",
        f"  Generated    : {now}",
        f"  Script file  : {script_filename}",
        f"  Validation   : {val_status}",

        sec("GDS File"),
        f"  Local path   : {cfg['gds_file_local']}",
        f"  Server path  : {cfg['gds_file_server']}",
        f"  GDS cell     : {cfg.get('cell_name', 'TOP')}",

        sec("Substrate"),
        f"  Material     : {cfg['substrate_material']}",
        f"  Thickness    : {cfg['substrate_thickness']} µm",
        f"  Doping       : {dop['concentration']:.2e} cm⁻³  ({dop['dopant']})",

        sec("Extraction Window"),
        f"  X            : {ext['x_from']} → {ext['x_to']} µm",
        f"  Y cut        : {ext['y_at']} µm",
        f"  Resolution   : {cfg['resolution']} µm",

        sec("Simulation Settings"),
        f"  Threads      : {sim.get('num_threads', 24)}",
        f"  Memory limit : {sim.get('memory_limit_mb', 128)} MB",
        f"  Notation     : {sim.get('notation', 'scientific')}",

        sec(f"Process Stack  ({len(layers)} steps)"),
    ]

    if layers:
        for i, layer in enumerate(layers, start=1):
            mat_col = f"{layer['material']:<22s}"
            lines.append(f"  Step {i:2d}      : {mat_col}  {layer['thickness']} µm")
    else:
        lines.append("  (no additional process steps defined)")

    if val_lines:
        lines.append(sec("Validation Issues"))
        for vl in val_lines:
            lines.append(f"  {vl}")

    lines += [
        sec("Output Artifacts"),
        f"  {script_filename:<30s}Victory Process script",
        f"  config.json                    Reproducible config (for reruns)",
        f"  summary.txt                    This file",
        f"  metadata.log                   Detailed run log",

        sec("Server Deployment"),
        "  1. Transfer this run directory to the server:",
        "       scp -r <run_dir>/ jjhanfli@grendel.ece.ncsu.edu:/mnt/ncsudrive/jjhanfli/",
        "  2. Confirm GDS is accessible at:",
        f"       {cfg['gds_file_server']}",
        "  3. Load Silvaco and launch DeckBuild:",
        "       ml silvaco/2022",
        f"       deckbuild -run {script_filename} -outfile run.log",
        "  4. Visualize output in TonyPlot:",
        f"       tonyplot {cfg['project_name']}_Final.str",
        "",
        "=" * W,
    ]

    (run_dir / "summary.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
