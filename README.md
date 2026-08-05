# ASCEND v1.1.0 — Automated TCAD Script ENgineering for Device Simulation

A lightweight Python pipeline that converts a KLayout GDS mask design into a
reproducible Silvaco Victory Process simulation script.

Developed as part of the ASCEND Research Program, NC State University ECE Dept,
LEADS Research Group under Dr. Spyridon Pavlidis.

---

## Conceptual Architecture

```
CLI Input
    │
    ▼
TCADConfig  ←──  Materials DB (with process_mode)
    │
    ├─▶ Syntax Validation    (config.py)
    │       "Is this well-formed?"
    │
    ├─▶ Semantic Validation  (validator.py)
    │       "Does this make physical sense?"
    │
    ▼
ScriptGenerator             (generator.py)
    │   dispatches on material.process_mode
    │   no material-name logic in generator
    ▼
Victory Process .in script
    │
    ├── config.json
    ├── summary.txt
    └── metadata.log
    │
    │  SCP / MobaXterm transfer
    ▼
NC State Linux Server → DeckBuild → TonyPlot (.str output)
```

---

## File Structure

```
tcad_pipeline/
├── main.py          Entry point: orchestrates all stages
├── cli.py           Interactive prompts → TCADConfig
├── config.py        Typed dataclasses + syntax validation + JSON I/O
├── materials.py     Material DB + process_mode + alias normalization
├── generator.py     TCADConfig → Victory Process .in (pure function)
├── validator.py     Semantic / engineering sanity checks (TCADValidator)
├── gds_tools.py     Optional GDS cell-existence check
└── run_manager.py   Timestamped output dirs, logging, summary.txt
```

---

## Quick Start

```bash
# Interactive run
python main.py

# Replay a previous run exactly (no prompts)
python main.py --from output/MyDevice_2024-01-15_143022/config.json
```

---

## Validation Pipeline (Two Stages)

**Stage 1 — Syntax (config.py)**
Checks: required fields present, GDS file exists, numbers are positive,
extraction window is correctly ordered, project name has no illegal characters.
Raises immediately with a clear message.

**Stage 2 — Semantic (validator.py)**
Checks: resolution within realistic TCAD range (0.001–10 µm), substrate
thickness in physical range, extraction window not absurdly large (catches
nm-entered-as-µm mistakes), layer thicknesses in bounds, duplicate
consecutive layers, optional GDS cell-name verification.
Returns a list of issues by severity — errors halt the pipeline, warnings
are shown and recorded but don't block it.

---

## Key Design Decisions

### Two GDS Paths
`gds_file_local` — validated on your Windows machine (must exist).
`gds_file_server` — goes inside the .in script (path on Linux server).
Default server path: just the filename, relative to DeckBuild's working dir.

This prevents the classic bug where `C:\Users\jjhan\...` ends up inside
a DeckBuild script and crashes immediately on the server.

### process_mode on Material objects
Each material carries `process_mode: "deposit" | "mask" | "etch" | "implant"`.
The generator dispatches on this field — no material names are hardcoded
inside generator.py. Adding new process behaviors only requires updating
materials.py.

### SimulationSettings
`num_threads`, `memory_limit_mb`, and `notation` are now configurable,
not hardcoded as `-P 24 -128`. Use `notation="compact"` if you get parser
errors from Victory Process on doping values — it emits `2e19` instead of
`2.000e+19`.

### Timestamped Run Directories
Every run writes to `output/<project>_<timestamp>/`. Nothing is ever
overwritten. The saved `config.json` is enough to reproduce the identical
script on any machine.

---

## Supported Materials

| Input alias(es)                  | Canonical name   | Silvaco name | process_mode |
|----------------------------------|------------------|--------------|--------------|
| si, silicon                      | Silicon          | Silicon      | deposit      |
| sio2, oxide, silicon dioxide     | SiO2             | SiO2         | deposit      |
| resist, photoresist, pr          | Photoresist      | resist       | mask         |
| al, aluminum, aluminium          | Aluminum         | Aluminum     | deposit      |
| ni, nickel                       | Nickel           | Nickel       | deposit      |
| cu, copper                       | Copper           | Copper       | deposit      |
| poly, polysilicon                | Polysilicon      | Polysilicon  | deposit      |
| sin, si3n4, nitride              | Silicon Nitride  | Si3N4        | deposit      |
| tin, titanium nitride            | TiN              | TiN          | deposit      |
| ti, titanium                     | Titanium         | Titanium     | deposit      |
| au, gold                         | Gold             | Gold         | deposit      |
| w, tungsten                      | Tungsten         | Tungsten     | deposit      |

---

## Optional: GDS Cell Validation

If `gdspy` is installed, ASCEND will verify that the cell name (e.g. "TOP")
actually exists in your GDS file before generating the script:

```bash
pip install gdspy
```

If neither `gdspy` nor the KLayout Python API is available, this check is
gracefully skipped with an info note in summary.txt.

---

## Server Deployment Checklist

- [ ] `Test_Mask.gds` transferred to `/mnt/ncsudrive/jjhanfli/Import Mask/`
- [ ] Server path in config matches GDS location exactly
- [ ] .in script and GDS in same directory OR GDS path is absolute in script
- [ ] DeckBuild license loaded: `ml silvaco/2022`
- [ ] Run: `deckbuild -run <project>.in -outfile run.log`
- [ ] Check run.log for errors before opening TonyPlot
- [ ] Visualize: `tonyplot <project>_Final.str`

---

## Extending the Pipeline

**New material**: add to `MATERIAL_DB` and `_ALIASES` in `materials.py`.

**New process command** (e.g. ETCH): add `"etch"` to a material's
`process_mode`, then add the matching branch in
`ScriptGenerator._process_steps()`.

**Batch parameter sweep**: call `run_pipeline(config)` in a loop from a
separate script. Each call produces its own timestamped output directory.

**Headless / scripted use**:
```python
from config import TCADConfig, DopingConfig
from main import run_pipeline
config = TCADConfig.from_json(Path("output/MyDevice_.../config.json"))
run_pipeline(config)
```
