"""
gui.py — ASCEND TCAD Pipeline (Streamlit Web Interface)
Allows users to configure, validate, preview, and generate Silvaco Victory 
Process scripts directly in a browser. Designed for sharing with research collaborators and PIs.
"""

import streamlit as st
from pathlib import Path
import io
import zipfile
import tempfile

from config import TCADConfig, DopingConfig, ExtractionWindow, LayerConfig, SimulationSettings, ASCEND_VERSION
from materials import MATERIAL_DB, normalize_material, get_material
from validator import TCADValidator
from generator import ScriptGenerator
from run_manager import write_summary

st.set_page_config(
    page_title=f"ASCEND TCAD Generator v{ASCEND_VERSION}",
    page_icon="⚡",
    layout="wide",
)

st.title("⚡ ASCEND TCAD Automation Tool")
st.markdown(f"**Silvaco Victory Process Script Generator v{ASCEND_VERSION}** — NC State University ECE Dept / LEADS Research Group")
st.markdown("---")

# ── Session State Initialization for Dynamic Layers ───────────────────────────
if "layers" not in st.session_state:
    st.session_state.layers = [
        {"material": "SiO2", "thickness": 0.5},
        {"material": "Photoresist", "thickness": 1.2}
    ]

# ── Sidebar Configuration ─────────────────────────────────────────────────────
st.sidebar.header("Simulation Parameters")

with st.sidebar.expander("1. Project & GDS", expanded=True):
    project_name = st.text_input("Project Name", value="MyDevice")
    output_dir = st.text_input("Output Directory", value="output")
    gds_local = st.text_input("Local GDS File Path", value="Test_Mask.gds")
    gds_server = st.text_input("Server-side GDS Path (for .in script)", value="Test_Mask.gds")
    cell_name = st.text_input("GDS Top Cell Name", value="TOP")

with st.sidebar.expander("2. Substrate & Doping", expanded=False):
    substrate_material = st.selectbox("Substrate Material", ["Silicon", "GaAs"], index=0)
    substrate_thickness = st.number_input("Substrate Thickness (µm)", min_value=0.01, max_value=1000.0, value=8.0, step=0.5)
    dopant_type = st.selectbox("Dopant Type", ["phosphorus", "boron", "arsenic", "antimony"], index=0)
    doping_concentration = st.text_input("Doping Concentration (cm⁻³)", value="2e19")

with st.sidebar.expander("3. Extraction Window", expanded=False):
    col1, col2 = st.columns(2)
    with col1:
        x_from = st.number_input("FROM X (µm)", value=-3.0, step=0.5)
    with col2:
        x_to = st.number_input("TO X (µm)", value=3.0, step=0.5)
    y_at = st.number_input("AT Y (µm)", value=0.0, step=0.5)
    resolution = st.number_input("Mesh Resolution (µm)", min_value=0.001, max_value=10.0, value=1.0, step=0.1)

with st.sidebar.expander("4. Simulation Solver Settings", expanded=False):
    num_threads = st.number_input("CPU Threads (-P flag)", min_value=1, max_value=256, value=24)
    memory_limit_mb = st.number_input("Memory Limit (MB)", min_value=1, max_value=8192, value=128)
    notation = st.selectbox("Doping Number Notation", ["scientific", "compact"], index=0)

# ── Main Area: Process Stack Management ───────────────────────────────────────
st.subheader("Process Stack Architecture")
st.markdown("Configure deposition, masking, and etch steps in sequential order.")

available_materials = sorted(list(MATERIAL_DB.keys()))

for idx, layer in enumerate(st.session_state.layers):
    cols = st.columns([3, 2, 1])
    with cols[0]:
        mat_choice = st.selectbox(
            f"Material — Step {idx+2}",
            available_materials,
            index=available_materials.index(layer["material"]) if layer["material"] in available_materials else 0,
            key=f"mat_{idx}"
        )
        st.session_state.layers[idx]["material"] = mat_choice
    with cols[1]:
        thick_val = st.number_input(
            f"Thickness (µm) — Step {idx+2}",
            min_value=0.0001,
            max_value=200.0,
            value=float(layer["thickness"]),
            step=0.1,
            key=f"thick_{idx}"
        )
        st.session_state.layers[idx]["thickness"] = thick_val
    with cols[2]:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Remove", key=f"rem_{idx}"):
            st.session_state.layers.pop(idx)
            st.rerun()

if st.button("＋ Add Process Layer"):
    st.session_state.layers.append({"material": "Aluminum", "thickness": 1.0})
    st.rerun()

st.markdown("---")

# ── Build Configuration & Validation Logic ───────────────────────────────────
try:
    concentration_float = float(doping_concentration)
except ValueError:
    concentration_float = 2e19

# Construct config object
try:
    config = TCADConfig(
        project_name=project_name,
        gds_file_local=gds_local,
        gds_file_server=gds_server,
        substrate_material=substrate_material,
        substrate_thickness=substrate_thickness,
        doping=DopingConfig(dopant=dopant_type, concentration=concentration_float),
        extraction=ExtractionWindow(x_from=x_from, x_to=x_to, y_at=y_at),
        cell_name=cell_name,
        resolution=resolution,
        layers=[LayerConfig(material=l["material"], thickness=l["thickness"]) for l in st.session_state.layers],
        simulation=SimulationSettings(
            num_threads=num_threads,
            memory_limit_mb=memory_limit_mb,
            notation=notation
        ),
        output_dir=output_dir,
    )
    config_valid = True
    config_error = None
except Exception as e:
    config_valid = False
    config_error = str(e)

# ── Validation & Generation Display Tabs ─────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["🚀 Script Preview", "🔍 Validation Report", "📦 Export Artifacts"])

with tab1:
    st.subheader("Generated Victory Process Script (.in)")
    if config_valid:
        try:
            generator = ScriptGenerator(config)
            script_text = generator.generate()
            st.code(script_text, language="tcl")
        except Exception as gen_err:
            st.error(f"Error generating script: {gen_err}")
    else:
        st.error(f"Configuration Syntax Error: {config_error}")

with tab2:
    st.subheader("Two-Stage Validation Analysis")
    if not config_valid:
        st.error(f"Syntax Validation Failed:\n{config_error}")
    else:
        st.success("✓ Syntax validation passed.")
        
        # Run semantic validation
        validator = TCADValidator(config)
        issues = validator.validate()
        
        errors = [i for i in issues if i.severity == "error"]
        warnings = [i for i in issues if i.severity == "warning"]
        infos = [i for i in issues if i.severity == "info"]

        if errors:
            st.error(f"Found {len(errors)} Engineering Error(s):")
            for err in errors:
                st.markdown(f"- **[{err.code}]** {err.message}")
        if warnings:
            st.warning(f"Found {len(warnings)} Engineering Warning(s):")
            for warn in warnings:
                st.markdown(f"- **[{warn.code}]** {warn.message}")
        if infos:
            for inf in infos:
                st.info(f"**[{inf.code}]** {inf.message}")
        
        if not errors and not warnings:
            st.success("✓ All engineering sanity checks passed successfully.")

with tab3:
    st.subheader("Download Simulation Package")
    st.markdown("Generate and download a complete archive containing the `.in` script, `config.json`, and run summary for server deployment.")

    if config_valid:
        if st.button("Build & Package Simulation Run"):
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_path = Path(tmpdir)
                run_dir = tmp_path / f"{config.project_name}_run"
                run_dir.mkdir(parents=True, exist_ok=True)

                # Generate files
                script_filename = f"{config.project_name}.in"
                script_text = ScriptGenerator(config).generate()
                (run_dir / script_filename).write_text(script_text, encoding="utf-8")
                config.save_json(run_dir / "config.json")
                
                validator = TCADValidator(config)
                issues = validator.validate()
                write_summary(run_dir, config.to_dict(), script_filename, issues)

                # Create ZIP in memory
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                    for file_path in run_dir.glob("*"):
                        zip_file.write(file_path, arcname=file_path.name)
                zip_buffer.seek(0)

                st.download_button(
                    label="📥 Download Run Package (.zip)",
                    data=zip_buffer,
                    file_name=f"{config.project_name}_run_package.zip",
                    mime="application/zip",
                )
                st.success("Package built successfully. Ready for download and server transfer.")
    else:
        st.warning("Resolve syntax errors before generating export packages.")
