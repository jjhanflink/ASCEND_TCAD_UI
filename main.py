"""
main.py — ASCEND TCAD Pipeline
Entry point. Orchestrates the full pipeline:

  CLI → TCADConfig → Syntax Validation → Semantic Validation
  → Script Generation → Artifact Management

Usage:
    python main.py                        Interactive mode
    python main.py --from config.json     Replay a previous run exactly
"""

import sys
import argparse
from pathlib import Path

from config import TCADConfig, ASCEND_VERSION
from cli import collect_config
from generator import ScriptGenerator
from validator import TCADValidator
from run_manager import (
    create_run_dir, setup_logger, write_summary, log_system_info
)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="main.py",
        description=f"ASCEND TCAD Automation Tool v{ASCEND_VERSION}",
    )
    p.add_argument(
        "--from",
        dest="config_json",
        metavar="config.json",
        help="Replay a previous run from its saved config.json.",
    )
    return p.parse_args()


def run_pipeline(config: TCADConfig) -> int:
    """Execute the full pipeline for a given config. Returns 0 (ok) or 1 (error)."""

    # ── Stage 1: Syntax validation ────────────────────────────────────────────
    print("\n  Checking configuration (syntax)...")
    try:
        config.validate()
    except (ValueError, FileNotFoundError) as e:
        print(f"\n  ✗  Validation failed:\n")
        for line in str(e).splitlines():
            print(f"       {line}")
        print()
        return 1
    print("  ✓  Syntax OK.")

    # ── Stage 2: Semantic validation ──────────────────────────────────────────
    print("  Checking configuration (engineering sanity)...")
    issues = TCADValidator(config).validate()
    errors   = [i for i in issues if i.severity == "error"]
    warnings = [i for i in issues if i.severity == "warning"]
    infos    = [i for i in issues if i.severity == "info"]

    if infos:
        for issue in infos:
            print(f"    ℹ  {issue.message}")
    if warnings:
        print()
        for issue in warnings:
            print(f"    ⚠  [{issue.code}] {issue.message}")
    if errors:
        print()
        for issue in errors:
            print(f"    ✗  [{issue.code}] {issue.message}")
        print("\n  ✗  Engineering validation failed. Correct the above and re-run.\n")
        return 1

    if warnings:
        print(f"\n  ⚠  {len(warnings)} warning(s) noted above — review before running.")
    else:
        print("  ✓  Engineering checks passed.")

    # ── Stage 3: Create run directory + logging ───────────────────────────────
    run_dir = create_run_dir(config.output_dir, config.project_name)
    logger = setup_logger(run_dir, config.project_name)
    log_system_info(logger)
    logger.info("Run started  →  project: %s", config.project_name)
    logger.info("Run directory: %s", run_dir.resolve())

    for issue in issues:
        logger.debug("Validation: %s", issue)

    # ── Stage 4: Generate Victory Process script ──────────────────────────────
    logger.info("Generating Victory Process script...")
    script_text = ScriptGenerator(config).generate()
    script_filename = f"{config.project_name}.in"
    (run_dir / script_filename).write_text(script_text, encoding="utf-8")
    logger.info("Script written: %s", script_filename)

    # ── Stage 5: Save config JSON ─────────────────────────────────────────────
    config.save_json(run_dir / "config.json")
    logger.info("Config saved:  config.json")

    # ── Stage 6: Write summary ────────────────────────────────────────────────
    write_summary(run_dir, config.to_dict(), script_filename, issues)
    logger.info("Summary written: summary.txt")
    logger.info("Pipeline complete.")

    # ── Done ──────────────────────────────────────────────────────────────────
    W = 62
    print(f"\n  {'─' * W}")
    print(f"  ✓  Done. Artifacts saved to:")
    print(f"     {run_dir.resolve()}")
    print()
    print(f"  Files generated:")
    print(f"    {script_filename:<34s}Victory Process script")
    print(f"    config.json                        Reproducible config")
    print(f"    summary.txt                        Human-readable run record")
    print(f"    metadata.log                       Detailed log")
    print()
    print(f"  Next steps on the server:")
    print(f"    1. scp -r \"{run_dir}\" jjhanfli@grendel.ece.ncsu.edu:/mnt/ncsudrive/jjhanfli/")
    print(f"    2. Confirm GDS at: {config.gds_file_server}")
    print(f"    3. ml silvaco/2022")
    print(f"    4. deckbuild -run {script_filename} -outfile run.log")
    print(f"    5. tonyplot {config.project_name}_Final.str")
    print(f"  {'─' * W}\n")

    return 0


def main() -> int:
    args = _parse_args()

    if args.config_json:
        json_path = Path(args.config_json)
        if not json_path.exists():
            print(f"\n  ✗  Config file not found: {args.config_json}\n")
            return 1
        print(f"\n  Loading config from: {json_path.resolve()}")
        config = TCADConfig.from_json(json_path)
        print(f"  Project: {config.project_name}")
    else:
        try:
            config = collect_config()
        except KeyboardInterrupt:
            print("\n\n  Aborted.\n")
            return 0

    return run_pipeline(config)


if __name__ == "__main__":
    sys.exit(main())
