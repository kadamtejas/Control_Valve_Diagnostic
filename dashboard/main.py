"""
main.py - FastAPI backend for Valve Diagnostics POC (with auth + upload + background jobs)

Run with:
    cd D:\\desktop\\Ingenero\\Valve_Diagnostic_Tool_POC\\dashboard
    python -m uvicorn main:app --reload --port 8001

Then open: http://localhost:8001
"""

import json
import os
import shutil
import subprocess
import sys
import threading
import uuid
from pathlib import Path

from fastapi import (
    Depends, FastAPI, File, HTTPException, Request, UploadFile, status
)
from fastapi.responses import (
    FileResponse, HTMLResponse, JSONResponse, RedirectResponse
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from auth import authenticate_user, create_access_token, get_current_user
from reader import (
    read_all_loop_names,
    read_dashboard_data,
    read_loop_timeseries,
    read_unit_mapping,
)

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR      = Path(__file__).parent.parent   # …/Valve_Diagnostic_Tool_POC
DASHBOARD_DIR = Path(__file__).parent
UPLOADS_DIR   = BASE_DIR / "uploads"
UPLOADS_DIR.mkdir(exist_ok=True)

# ── Paths
DEFAULT_CONFIG_PATH = BASE_DIR / "dashboard" / "default_config.json"
USER_CONFIG_DIR = BASE_DIR / "user_configs"
USER_CONFIG_DIR.mkdir(exist_ok=True)

# ── In-memory state ───────────────────────────────────────────────────────────
# { email: "results_My_plant_data_1" }          — active results folder per user
user_results: dict[str, str] = {}

# { job_id: { "status": "running"|"done"|"error", "results_dir": "...", "detail": "..." } }
jobs: dict[str, dict] = {}

# { email: { "dest_path": ..., "results_folder": ..., "mode": ... } } — awaiting config confirmation
pending_uploads: dict[str, dict] = {}

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="Valve Diagnostics POC", version="2.0.0")

templates = Jinja2Templates(directory=str(DASHBOARD_DIR / "templates"))

static_dir = DASHBOARD_DIR / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _results_dir_for(email: str) -> str | None:
    """Return the absolute results folder path for this user, or None.
    Falls back to the most recently modified results_* folder so the
    dashboard still works after a server restart.
    """
    folder = user_results.get(email)
    if folder:
        full = BASE_DIR / folder
        if full.exists():
            return str(full)
    # Fallback: auto-detect latest results folder
    from reader import find_latest_results_dir
    latest = find_latest_results_dir(str(BASE_DIR))
    if latest:
        # Register it so subsequent calls are fast
        user_results[email] = os.path.basename(latest)
        return latest
    return None


def _run_engine_background(job_id: str, input_path: Path, results_folder: str, mode: str):
    """
    Runs in a background thread.
    Calls valve_diagnostics_v3.py via subprocess exactly like the bat files do:
      AUTO:   python valve_diagnostics_v3.py --input <file> --output-dir <dir>
      MANUAL: python valve_diagnostics_v3.py --input <file> --output-dir <dir> --manual
    cwd = BASE_DIR (same as 'cd /d %~dp0' in the bat file).
    """
    cmd = [
        sys.executable,
        str(BASE_DIR / "valve_diagnostics_v3.py"),
        "--input", str(input_path),
        "--output-dir", str(BASE_DIR / results_folder),
    ]
    if mode == "manual":
        cmd.append("--manual")

    try:
        result = subprocess.run(
            cmd,
            cwd=str(BASE_DIR),          # critical — engine uses relative paths internally
            capture_output=True,
            encoding='utf-8',
            errors='replace',
        )
        if result.returncode == 0:
            jobs[job_id]["status"] = "done"
        elif result.returncode == 2:
            jobs[job_id]["status"] = "error"
            jobs[job_id]["detail"] = "Health check failed — check your Excel file format."
        else:
            jobs[job_id]["status"] = "error"
            jobs[job_id]["detail"] = (
                f"Engine exited with code {result.returncode}. "
                f"{result.stderr[-400:] if result.stderr else ''}"
            )
    except Exception as exc:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["detail"] = str(exc)


# ── Config helpers ────────────────────────────────────────────────────────────

def _get_user_config_path(email: str) -> Path:
    safe = email.replace("@", "_at_").replace(".", "_")
    return USER_CONFIG_DIR / f"{safe}.json"


def _load_config(email: str) -> dict:
    """Load user config, falling back to default."""
    user_path = _get_user_config_path(email)
    if user_path.exists():
        with open(user_path, encoding="utf-8") as f:
            return json.load(f)
    if DEFAULT_CONFIG_PATH.exists():
        with open(DEFAULT_CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"diagnostic_config": [], "diagnostic_selection": [], "mode_mapping": []}


def _save_config(email: str, config: dict):
    path = _get_user_config_path(email)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


def _write_config_to_excel(input_path: Path, config: dict):
    """Overwrite DIAGNOSTIC_CONFIG, DIAGNOSTIC_SELECTION, MODE_MAPPING sheets."""
    import openpyxl
    wb = openpyxl.load_workbook(str(input_path))

    # DIAGNOSTIC_CONFIG
    if "DIAGNOSTIC_CONFIG" in wb.sheetnames:
        ws = wb["DIAGNOSTIC_CONFIG"]
        for i, row in enumerate(config.get("diagnostic_config", []), start=2):
            ws.cell(i, 1, row["parameter"])
            ws.cell(i, 2, row["value"])
            ws.cell(i, 3, row.get("description", ""))

    # DIAGNOSTIC_SELECTION — write with leading spaces preserved
    if "DIAGNOSTIC_SELECTION" in wb.sheetnames:
        ws = wb["DIAGNOSTIC_SELECTION"]
        for i, row in enumerate(config.get("diagnostic_selection", []), start=2):
            indent = row.get("indent", 0)
            name = ("    " * indent) + row["diagnostic"]
            ws.cell(i, 1, name)
            ws.cell(i, 2, row["enabled"])

    # MODE_MAPPING
    if "MODE_MAPPING" in wb.sheetnames:
        ws = wb["MODE_MAPPING"]
        # Clear existing data rows
        for row in ws.iter_rows(min_row=2, max_row=ws.max_row):
            for cell in row:
                cell.value = None
        for i, row in enumerate(config.get("mode_mapping", []), start=2):
            ws.cell(i, 1, row["category"])
            ws.cell(i, 2, row["value"])

    wb.save(str(input_path))


# ── Auth endpoints ────────────────────────────────────────────────────────────

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"error": None})


@app.post("/login")
async def login_submit(request: Request):
    form     = await request.form()
    email    = form.get("email", "").strip()
    password = form.get("password", "")

    user = authenticate_user(email, password)
    if not user:
        return templates.TemplateResponse(
            request, "login.html",
            {"error": "Invalid email or password."},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    token    = create_access_token(user)
    response = RedirectResponse(url="/upload", status_code=302)
    response.set_cookie(
        key="access_token", value=token,
        httponly=True, samesite="lax", max_age=8 * 3600,
    )
    return response


@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("access_token")
    return response


# ── Upload endpoints ──────────────────────────────────────────────────────────

@app.get("/upload", response_class=HTMLResponse)
async def upload_page(request: Request, current_user: dict = Depends(get_current_user)):
    return templates.TemplateResponse(request, "upload.html", {"user": current_user})


@app.post("/upload")
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    # ── Validate extension
    if not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Only .xlsx / .xls files are accepted.")

    # ── Read mode from form (auto | manual)
    form = await request.form()
    mode = form.get("mode", "auto").lower()
    if mode not in ("auto", "manual"):
        mode = "auto"

    # ── Save to POC root using ORIGINAL filename (engine derives results folder from it)
    original_name = Path(file.filename).name
    dest_path     = BASE_DIR / original_name
    with open(dest_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # ── Derive results folder name exactly like the bat files do
    basename       = Path(original_name).stem          # e.g. "My_plant_data_1"
    results_folder = f"results_{basename}" if mode == "auto" else f"results_{basename}_manual"

    # ── Load default/user config and write it into the Excel
    config = _load_config(current_user["sub"])
    try:
        _write_config_to_excel(dest_path, config)
    except Exception:
        pass  # Non-fatal — engine will use whatever is already in the file

    # ── Start engine immediately with defaults — no config page
    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "status":         "running",
        "results_folder": results_folder,
        "detail":         "",
        "email":          current_user["sub"],
    }
    thread = threading.Thread(
        target=_run_engine_background,
        args=(job_id, dest_path, results_folder, mode),
        daemon=True,
    )
    thread.start()

    # ── Also store as pending so the user can later open settings and re-run
    pending_uploads[current_user["sub"]] = {
        "dest_path":      str(dest_path),
        "results_folder": results_folder,
        "mode":           mode,
        "original_name":  original_name,
    }

    return JSONResponse({"status": "running", "job_id": job_id})


# ── Job polling endpoint ──────────────────────────────────────────────────────

@app.get("/api/job/{job_id}")
async def poll_job(job_id: str, current_user: dict = Depends(get_current_user)):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    # Only the user who started the job can poll it
    if job["email"] != current_user["sub"]:
        raise HTTPException(status_code=403, detail="Not your job.")

    if job["status"] == "done":
        # Register results folder for this user
        user_results[current_user["sub"]] = job["results_folder"]
        return JSONResponse({"status": "done", "redirect": "/"})

    if job["status"] == "error":
        return JSONResponse({"status": "error", "detail": job.get("detail", "Unknown error.")})

    return JSONResponse({"status": "running"})


# ── Config endpoints ──────────────────────────────────────────────────────────

@app.get("/config", response_class=HTMLResponse)
async def config_page(request: Request, current_user: dict = Depends(get_current_user)):
    # Config page is no longer shown automatically — redirect to dashboard
    return RedirectResponse(url="/", status_code=302)


@app.get("/api/config")
async def get_config(current_user: dict = Depends(get_current_user)):
    config = _load_config(current_user["sub"])
    return JSONResponse(content=config)


@app.post("/api/config/run")
async def save_config_and_run(request: Request, current_user: dict = Depends(get_current_user)):
    pending = pending_uploads.get(current_user["sub"])
    if not pending:
        raise HTTPException(status_code=400, detail="No pending upload. Please upload a file first.")

    config = await request.json()

    # Save user config
    _save_config(current_user["sub"], config)

    # Write config back into the Excel
    dest_path = Path(pending["dest_path"])
    try:
        _write_config_to_excel(dest_path, config)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to write config to Excel: {e}")

    # Now start engine
    results_folder = pending["results_folder"]
    mode = pending["mode"]
    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "status":         "running",
        "results_folder": results_folder,
        "detail":         "",
        "email":          current_user["sub"],
    }
    thread = threading.Thread(
        target=_run_engine_background,
        args=(job_id, dest_path, results_folder, mode),
        daemon=True,
    )
    thread.start()

    # Clear pending
    pending_uploads.pop(current_user["sub"], None)

    return JSONResponse({"job_id": job_id, "status": "running"})


# ── Re-run with new settings (called from the Settings panel on the dashboard) ──

@app.post("/api/config/rerun")
async def rerun_with_config(request: Request, current_user: dict = Depends(get_current_user)):
    pending = pending_uploads.get(current_user["sub"])
    if not pending:
        raise HTTPException(status_code=400, detail="No uploaded file found for your session. Please upload a file first.")

    config = await request.json()

    # Save user config
    _save_config(current_user["sub"], config)

    # Write config back into the Excel
    dest_path = Path(pending["dest_path"])
    try:
        _write_config_to_excel(dest_path, config)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to write config to Excel: {e}")

    # Start engine
    results_folder = pending["results_folder"]
    mode = pending["mode"]
    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "status":         "running",
        "results_folder": results_folder,
        "detail":         "",
        "email":          current_user["sub"],
    }
    thread = threading.Thread(
        target=_run_engine_background,
        args=(job_id, dest_path, results_folder, mode),
        daemon=True,
    )
    thread.start()

    return JSONResponse({"job_id": job_id, "status": "running"})


# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request, current_user: dict = Depends(get_current_user)):
    response = templates.TemplateResponse(request, "index.html", {"user": current_user})
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    return response


# ── API: results (always from THIS user's results folder) ────────────────────

def _get_user_results_dir(current_user: dict) -> str:
    rd = _results_dir_for(current_user["sub"])
    if not rd:
        raise HTTPException(
            status_code=404,
            detail="No results found for your session. Please upload a file first.",
        )
    return rd


@app.get("/api/latest")
async def get_latest(current_user: dict = Depends(get_current_user)):
    rd = _get_user_results_dir(current_user)
    try:
        data = read_dashboard_data(rd)
        return JSONResponse(content=data)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error reading results: {e}")


@app.get("/api/plots")
async def get_plots(current_user: dict = Depends(get_current_user)):
    rd = _get_user_results_dir(current_user)
    rd_path = Path(rd)
    plots = []
    for fname in ["diagnostic_heatmap.png", "plant_dashboard.png"]:
        if (rd_path / fname).exists():
            plots.append({"name": fname, "type": "overview", "url": f"/plot-image/{fname}"})
    plots_dir = rd_path / "plots"
    if plots_dir.exists():
        for f in sorted(plots_dir.iterdir()):
            if f.suffix.lower() == ".png":
                plots.append({"name": f.name, "type": "loop", "url": f"/plot-image/plots/{f.name}"})
    return JSONResponse(content={"plots": plots, "run_folder": rd_path.name})


@app.api_route("/plot-image/{file_path:path}", methods=["GET", "HEAD"])
async def serve_plot(file_path: str, request: Request, current_user: dict = Depends(get_current_user)):
    rd = _get_user_results_dir(current_user)
    full_path = Path(rd) / file_path
    if not full_path.exists():
        raise HTTPException(status_code=404, detail=f"Image not found: {file_path}")
    if request.method == "HEAD":
        return JSONResponse(status_code=200, content={})
    return FileResponse(str(full_path), media_type="image/png")


@app.get("/api/timeseries/{loop_name:path}")
async def get_timeseries(loop_name: str, current_user: dict = Depends(get_current_user)):
    rd = _get_user_results_dir(current_user)
    try:
        data = read_loop_timeseries(rd, loop_name)
        return JSONResponse(content=data)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading time series: {e}")


@app.get("/api/loops")
async def get_loop_names(current_user: dict = Depends(get_current_user)):
    rd = _get_user_results_dir(current_user)
    loops = read_all_loop_names(rd)
    return JSONResponse(content={"loops": loops})


@app.get("/api/unit-mapping")
async def get_unit_mapping(current_user: dict = Depends(get_current_user)):
    rd = _get_user_results_dir(current_user)
    data = read_unit_mapping(rd, str(BASE_DIR))
    return JSONResponse(content=data)


@app.post("/api/unit-mapping/save")
async def save_unit_mapping(request: Request, current_user: dict = Depends(get_current_user)):
    """
    Persist the unit mapping sent from the UI.
    Payload: { "unit_mapping": { "loopTag": "unitName", ... } }
    The mapping is written back into the UNIT_MAPPING sheet of the original
    input Excel file so it survives server restarts.
    """
    body = await request.json()
    unit_mapping: dict = body.get("unit_mapping", {})
    if not isinstance(unit_mapping, dict):
        raise HTTPException(status_code=400, detail="unit_mapping must be an object.")

    # ── Find the input Excel for this user's current results folder ──────────
    rd = _get_user_results_dir(current_user)
    folder_name = os.path.basename(rd)
    stem = folder_name.removeprefix("results_").removesuffix("_manual")
    input_path = BASE_DIR / f"{stem}.xlsx"

    if not input_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Source file '{stem}.xlsx' not found. Please upload the file again.",
        )

    # ── Write UNIT_MAPPING sheet ─────────────────────────────────────────────
    try:
        import openpyxl
        wb = openpyxl.load_workbook(str(input_path))

        # Create sheet if missing
        if "UNIT_MAPPING" not in wb.sheetnames:
            ws = wb.create_sheet("UNIT_MAPPING")
            ws.cell(1, 1, "Tag")
            ws.cell(1, 2, "Unit")
        else:
            ws = wb["UNIT_MAPPING"]
            # Clear existing data rows
            for row in ws.iter_rows(min_row=2, max_row=ws.max_row):
                for cell in row:
                    cell.value = None

        for i, (tag, unit) in enumerate(unit_mapping.items(), start=2):
            ws.cell(i, 1, str(tag).strip())
            ws.cell(i, 2, str(unit).strip())

        wb.save(str(input_path))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to write unit mapping: {exc}")

    return JSONResponse(content={"status": "ok", "saved": len(unit_mapping)})


# ── Report download ───────────────────────────────────────────────────────────

@app.get("/api/report/download")
async def download_report(current_user: dict = Depends(get_current_user)):  # noqa: C901
    """
    Generates and returns a comprehensive PDF report combining:
      - Plant Health Summary  (Loop_diagnostics_v2.xlsx → Plant_Dashboard sheet)
      - Per-loop diagnosis with full explanations (Summary sheet)
      - Outlier handling section (outlier_handling_report.txt)
    """
    import io, re, math
    from datetime import datetime
    from fastapi.responses import StreamingResponse

    rd = _get_user_results_dir(current_user)
    if not rd:
        raise HTTPException(status_code=404, detail="No results found. Run diagnostics first.")

    rd_path = Path(rd)
    xl_path  = rd_path / "Loop_diagnostics_v2.xlsx"
    out_path = rd_path / "outlier_handling_report.txt"

    if not xl_path.exists():
        raise HTTPException(status_code=404, detail="Loop_diagnostics_v2.xlsx not found in results folder.")

    # ── Imports ───────────────────────────────────────────────────────────────
    import pandas as pd
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        PageBreak, HRFlowable, Flowable,
    )
    from reportlab.graphics.shapes import (
        Drawing, Circle, Rect, String, Line, Wedge,
    )
    from reportlab.graphics import renderPDF

    # ── Helper: round a value safely ─────────────────────────────────────────
    def fmt(v, decimals=1):
        try:
            f = float(str(v))
            return f"{f:.{decimals}f}"
        except:
            return str(v) if str(v) not in ("nan", "None", "") else "—"

    # ── Read data ─────────────────────────────────────────────────────────────
    dash_df = pd.read_excel(xl_path, sheet_name="Plant_Dashboard", header=None)
    kpi, mode = {}, "kpi"
    for _, row in dash_df.iterrows():
        vals = [str(v).strip() if str(v) != "nan" else "" for v in row.values]
        if vals[0] == "Loop" and vals[1] == "Health":
            mode = "loops"; continue
        if mode == "kpi" and vals[0] and vals[1]:
            kpi[vals[0]] = vals[1]

    sum_df = pd.read_excel(xl_path, sheet_name="Summary")

    outlier_text = ""
    if out_path.exists():
        raw = out_path.read_text(encoding="utf-8", errors="ignore")
        outlier_text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f═─]', '', raw).strip()

    # ── Extract KPIs ──────────────────────────────────────────────────────────
    phi       = kpi.get("Plant Health Index (0-100)", "0")
    total     = kpi.get("Loops total", "0")
    analysed  = kpi.get("Loops analysed", "0")
    skipped   = kpi.get("Loops skipped", "0")
    good_pct  = kpi.get("% Good (>=75)", "0")
    poor_pct  = kpi.get("% Poor (50–74)", "0")
    crit_pct  = kpi.get("% Critical (<50)", "0")
    duration  = kpi.get("Duration (hours)", "—")
    interval  = kpi.get("Sample interval", "—")
    run_ts    = kpi.get("Run timestamp", "—")

    try:   phi_f = float(phi)
    except: phi_f = 0.0

    # ── Styles ────────────────────────────────────────────────────────────────
    NAVY  = colors.HexColor("#0f2744")
    BLUE  = colors.HexColor("#2e86de")
    OK    = colors.HexColor("#1a9e5a")
    WARN  = colors.HexColor("#d97706")
    CRIT  = colors.HexColor("#dc2626")
    LGREY = colors.HexColor("#f0f4f8")
    MGREY = colors.HexColor("#d8e2ec")
    DGREY = colors.HexColor("#6b8299")
    WHITE = colors.white
    OK_BG   = colors.HexColor("#e6f7ef")
    WARN_BG = colors.HexColor("#fef3e2")
    CRIT_BG = colors.HexColor("#fdf0ef")

    phi_color = OK if phi_f >= 75 else (WARN if phi_f >= 50 else CRIT)
    phi_bg    = OK_BG if phi_f >= 75 else (WARN_BG if phi_f >= 50 else CRIT_BG)

    styles = getSampleStyleSheet()
    def sty(name, **kw):
        s = styles[name].clone(name + str(id(kw)))
        for k, v in kw.items(): setattr(s, k, v)
        return s

    H1   = sty("Heading1", fontSize=20, textColor=NAVY,  spaceAfter=4,  spaceBefore=0,  fontName="Helvetica-Bold")
    H2   = sty("Heading2", fontSize=13, textColor=NAVY,  spaceAfter=6,  spaceBefore=16, fontName="Helvetica-Bold")
    H3   = sty("Heading3", fontSize=10, textColor=NAVY,  spaceAfter=3,  spaceBefore=0,  fontName="Helvetica-Bold")
    BODY = sty("Normal",   fontSize=9,  textColor=colors.HexColor("#3a5068"), spaceAfter=4, leading=14)
    META = sty("Normal",   fontSize=8,  textColor=DGREY, spaceAfter=2)
    CELL = sty("Normal",   fontSize=8,  textColor=colors.HexColor("#3a5068"), leading=12, spaceAfter=0)
    MONO_CELL = sty("Normal", fontSize=8, textColor=NAVY, fontName="Courier", leading=12, spaceAfter=0)

    def hr(color=MGREY, thick=0.5):
        return HRFlowable(width="100%", thickness=thick, color=color, spaceAfter=6, spaceBefore=6)

    def to_hex(c):
        """Convert a reportlab Color object to a 6-char hex string."""
        return '%02x%02x%02x' % (int(c.red*255), int(c.green*255), int(c.blue*255))

    def sev_color(sev):
        s = str(sev).upper()
        if s in ("FAIL","CRITICAL"): return CRIT
        if s in ("WARN","WARNING"):  return WARN
        return OK

    def sev_bg(sev):
        s = str(sev).upper()
        if s in ("FAIL","CRITICAL"): return CRIT_BG
        if s in ("WARN","WARNING"):  return WARN_BG
        return OK_BG

    def sev_hdr_bg(sev): pass
    def sev_hdr_accent(sev): pass
    def sev_act_bg(sev): pass

    # ── Custom Flowable: PHI Gauge ────────────────────────────────────────────
    class PhiGauge(Flowable):
        """Semicircle gauge for the Plant Health Index."""
        def __init__(self, phi_val, color, width=200, height=120):
            super().__init__()
            self.phi_val = phi_val
            self.color   = color
            self.width   = width
            self.height  = height

        def draw(self):
            c = self.canv
            cx = self.width / 2
            cy = 18          # baseline of the semicircle
            r_outer = 70
            r_inner = 48

            # Background arc (grey) — full 180°
            c.setStrokeColor(MGREY)
            c.setFillColor(LGREY)
            c.setLineWidth(0)
            # Draw as a filled annular sector using path
            def arc_path(cx, cy, r, start_deg, end_deg, steps=60):
                pts = []
                for i in range(steps + 1):
                    a = math.radians(start_deg + (end_deg - start_deg) * i / steps)
                    pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
                return pts

            # Full background ring
            outer_pts = arc_path(cx, cy, r_outer, 0, 180)
            inner_pts = arc_path(cx, cy, r_inner, 180, 0)
            p = c.beginPath()
            p.moveTo(*outer_pts[0])
            for pt in outer_pts[1:]: p.lineTo(*pt)
            for pt in inner_pts: p.lineTo(*pt)
            p.close()
            c.setFillColor(LGREY)
            c.drawPath(p, fill=1, stroke=0)

            # Colored fill arc — from left (180°) sweeping right by phi%
            fill_end = self.phi_val / 100.0 * 180.0
            if fill_end > 1:
                outer_pts2 = arc_path(cx, cy, r_outer, 180 - fill_end, 180)
                inner_pts2 = arc_path(cx, cy, r_inner, 180, 180 - fill_end)
                p2 = c.beginPath()
                p2.moveTo(*outer_pts2[0])
                for pt in outer_pts2[1:]: p2.lineTo(*pt)
                for pt in inner_pts2: p2.lineTo(*pt)
                p2.close()
                c.setFillColor(self.color)
                c.drawPath(p2, fill=1, stroke=0)

            # Centre white circle (donut hole look)
            c.setFillColor(WHITE)
            c.circle(cx, cy, r_inner - 2, fill=1, stroke=0)

            # PHI value text in centre
            c.setFillColor(self.color)
            c.setFont("Helvetica-Bold", 22)
            phi_str = f"{self.phi_val:.0f}"
            c.drawCentredString(cx, cy + 18, phi_str)
            c.setFont("Helvetica", 9)
            c.setFillColor(DGREY)
            c.drawCentredString(cx, cy + 6, "out of 100")

            # Scale labels
            c.setFont("Helvetica", 7)
            c.setFillColor(DGREY)
            c.drawCentredString(cx - r_outer - 4, cy - 4, "0")
            c.drawCentredString(cx, cy + r_outer + 8, "50")
            c.drawCentredString(cx + r_outer + 4, cy - 4, "100")

        def wrap(self, aw, ah):
            return self.width, self.height

    # ── Flowable: coloured stat tile (used in a Table cell) ───────────────────
    def stat_tile(label, value, sub, bg, val_color):
        """Returns a tiny table acting as a coloured tile."""
        tile_data = [[
            Paragraph(f'<font color="#{to_hex(val_color)}"><b>{value}</b></font>',
                      sty("Normal", fontSize=16, fontName="Helvetica-Bold", spaceAfter=0, leading=18)),
        ],[
            Paragraph(f'<b>{label}</b>',
                      sty("Normal", fontSize=8, textColor=NAVY, spaceAfter=0, leading=10)),
        ],[
            Paragraph(sub, sty("Normal", fontSize=7, textColor=DGREY, spaceAfter=0, leading=9)),
        ]]
        t = Table(tile_data, colWidths=[3.8*cm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,-1), bg),
            ("PADDING",    (0,0), (-1,-1), 8),
            ("ROUNDEDCORNERS", [6]),
            ("VALIGN",     (0,0), (-1,-1), "MIDDLE"),
            ("ALIGN",      (0,0), (-1,-1), "CENTER"),
        ]))
        return t

    # ── sorted loops (used in sections 2 and 3) ───────────────────────────────
    sorted_loops = sorted(
        sum_df.itertuples(),
        key=lambda r: float(str(r._4)) if str(r._4) not in ("nan","") else 999
    )

    # ── Build story ───────────────────────────────────────────────────────────
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm,
        title="Valve Diagnostics Report"
    )
    story = []

    # ══ COVER HEADER ══════════════════════════════════════════════════════════
    # Navy banner
    banner_data = [[
        Paragraph("<font color='#ffffff'><b>Valve Diagnostics</b></font>",
                  sty("Normal", fontSize=18, fontName="Helvetica-Bold", spaceAfter=0)),
        Paragraph(f"<font color='#7fd3ff'>Comprehensive Diagnostic Report</font><br/>"
                  f"<font color='#6a92b5' size='8'>Generated: {datetime.now().strftime('%d %b %Y, %H:%M')}</font>",
                  sty("Normal", fontSize=11, spaceAfter=0, leading=16)),
    ]]
    banner_tbl = Table(banner_data, colWidths=[7*cm, 10*cm])
    banner_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), NAVY),
        ("PADDING",    (0,0), (-1,-1), 14),
        ("VALIGN",     (0,0), (-1,-1), "MIDDLE"),
    ]))
    story.append(banner_tbl)
    story.append(Spacer(1, 0.5*cm))

    # ══ SECTION 1: PLANT HEALTH SUMMARY ══════════════════════════════════════
    story.append(Paragraph("1. Plant Health Summary", H2))

    # Gauge + stat tiles side by side
    try:
        n_good = int(float(total) * float(good_pct) / 100 + 0.5) if good_pct not in ("—","") else "—"
        n_poor = int(float(total) * float(poor_pct) / 100 + 0.5) if poor_pct not in ("—","") else "—"
        n_crit = int(float(total) * float(crit_pct) / 100 + 0.5) if crit_pct not in ("—","") else "—"
    except:
        n_good = n_poor = n_crit = "—"

    gauge = PhiGauge(phi_f, phi_color, width=210, height=130)

    tiles_data = [
        [stat_tile("CRITICAL", str(n_crit),  f"{fmt(crit_pct,0)}% of loops", CRIT_BG, CRIT)],
        [stat_tile("ATTENTION", str(n_poor), f"{fmt(poor_pct,0)}% of loops", WARN_BG, WARN)],
        [stat_tile("HEALTHY",  str(n_good),  f"{fmt(good_pct,0)}% of loops", OK_BG,   OK)],
    ]
    tiles_tbl = Table(tiles_data, colWidths=[4.2*cm], rowHeights=[3.8*cm]*3)
    tiles_tbl.setStyle(TableStyle([
        ("PADDING",  (0,0), (-1,-1), 4),
        ("VALIGN",   (0,0), (-1,-1), "MIDDLE"),
    ]))

    # Info strip below gauge
    info_data = [
        [Paragraph("<b>Total Loops</b>", sty("Normal", fontSize=8, textColor=DGREY, spaceAfter=0)),
         Paragraph("<b>Analysed</b>",    sty("Normal", fontSize=8, textColor=DGREY, spaceAfter=0)),
         Paragraph("<b>Duration</b>",    sty("Normal", fontSize=8, textColor=DGREY, spaceAfter=0)),
         Paragraph("<b>Interval</b>",    sty("Normal", fontSize=8, textColor=DGREY, spaceAfter=0)),
         Paragraph("<b>Run At</b>",      sty("Normal", fontSize=8, textColor=DGREY, spaceAfter=0))],
        [Paragraph(f"<b>{total}</b>",    sty("Normal", fontSize=13, textColor=NAVY, fontName="Helvetica-Bold", spaceAfter=0)),
         Paragraph(f"<b>{analysed}</b>", sty("Normal", fontSize=13, textColor=NAVY, fontName="Helvetica-Bold", spaceAfter=0)),
         Paragraph(f"<b>{fmt(duration,1)} hrs</b>", sty("Normal", fontSize=11, textColor=NAVY, fontName="Helvetica-Bold", spaceAfter=0)),
         Paragraph(f"<b>{interval}</b>", sty("Normal", fontSize=11, textColor=NAVY, fontName="Helvetica-Bold", spaceAfter=0)),
         Paragraph(f"{str(run_ts)[:16]}",sty("Normal", fontSize=8,  textColor=NAVY, spaceAfter=0))],
    ]
    info_tbl = Table(info_data, colWidths=[2.5*cm]*5)
    info_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), LGREY),
        ("GRID",       (0,0), (-1,-1), 0.4, MGREY),
        ("PADDING",    (0,0), (-1,-1), 7),
        ("ALIGN",      (0,0), (-1,-1), "CENTER"),
        ("VALIGN",     (0,0), (-1,-1), "MIDDLE"),
    ]))

    # Outer layout: gauge | tiles
    outer_data = [[gauge, tiles_tbl]]
    outer_tbl  = Table(outer_data, colWidths=[11*cm, 6*cm])
    outer_tbl.setStyle(TableStyle([
        ("VALIGN",  (0,0), (-1,-1), "MIDDLE"),
        ("PADDING", (0,0), (-1,-1), 0),
    ]))
    story.append(outer_tbl)
    story.append(Spacer(1, 0.3*cm))
    story.append(info_tbl)
    story.append(Spacer(1, 0.3*cm))

    # Interpretation banner
    if phi_f >= 75:
        interp = f"✔  Plant is in <b>good health</b> (PHI = {phi_f:.1f}/100). Most loops are performing within acceptable limits."
    elif phi_f >= 50:
        interp = f"⚠  Plant is in <b>moderate condition</b> (PHI = {phi_f:.1f}/100). Several loops need attention — review the critical loops below."
    else:
        interp = f"✘  Plant is in <b>poor condition</b> (PHI = {phi_f:.1f}/100). Immediate attention required. Prioritise the critical faults listed below."

    interp_tbl = Table([[Paragraph(interp, sty("Normal", fontSize=9, textColor=phi_color, fontName="Helvetica-Bold", spaceAfter=0))]],
                       colWidths=[17*cm])
    interp_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), phi_bg),
        ("PADDING",    (0,0), (-1,-1), 10),
        ("ROUNDEDCORNERS", [6]),
    ]))
    story.append(interp_tbl)

    # ── Diagnosis breakdown bar ───────────────────────────────────────────────
    story.append(Spacer(1, 0.4*cm))
    diag_counts = sum_df["Diagnosis"].value_counts()
    if not diag_counts.empty:
        diag_header = [Paragraph("<b>Fault Type</b>", sty("Normal", fontSize=8, textColor=WHITE, spaceAfter=0)),
                       Paragraph("<b>Count</b>",       sty("Normal", fontSize=8, textColor=WHITE, spaceAfter=0)),
                       Paragraph("<b>% of Loops</b>",  sty("Normal", fontSize=8, textColor=WHITE, spaceAfter=0))]
        diag_rows = [diag_header]
        total_l = int(float(total)) if str(total).replace(".","").isdigit() else 1
        for fault, cnt in diag_counts.items():
            pct = cnt / total_l * 100
            diag_rows.append([
                Paragraph(str(fault), CELL),
                Paragraph(str(cnt),   sty("Normal", fontSize=8, textColor=NAVY, fontName="Helvetica-Bold", spaceAfter=0)),
                Paragraph(f"{pct:.0f}%", CELL),
            ])
        diag_tbl = Table(diag_rows, colWidths=[11*cm, 2.5*cm, 3.5*cm])
        diag_tbl.setStyle(TableStyle([
            ("BACKGROUND",    (0,0), (-1,0), NAVY),
            ("TEXTCOLOR",     (0,0), (-1,0), WHITE),
            ("FONTSIZE",      (0,0), (-1,-1), 8),
            ("ROWBACKGROUNDS",(0,1), (-1,-1), [WHITE, LGREY]),
            ("GRID",          (0,0), (-1,-1), 0.4, MGREY),
            ("PADDING",       (0,0), (-1,-1), 6),
            ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        ]))
        story.append(Paragraph("Fault Distribution", sty("Normal", fontSize=10, textColor=NAVY, fontName="Helvetica-Bold", spaceAfter=4)))
        story.append(diag_tbl)

    # ══ SECTION 2: LOOP OVERVIEW ══════════════════════════════════════════════
    story.append(PageBreak())
    story.append(Paragraph("2. Loop Overview", H2))
    story.append(Paragraph(
        "All loops sorted from most critical to healthiest. "
        "Detailed analysis for each loop is in Section 3.", BODY))
    story.append(Spacer(1, 0.2*cm))

    # Header row
    ov_hdr = [
        Paragraph("<b>Loop</b>",      sty("Normal", fontSize=8, textColor=WHITE, spaceAfter=0)),
        Paragraph("<b>Severity</b>",  sty("Normal", fontSize=8, textColor=WHITE, spaceAfter=0)),
        Paragraph("<b>Health</b>",    sty("Normal", fontSize=8, textColor=WHITE, spaceAfter=0)),
        Paragraph("<b>Diagnosis</b>", sty("Normal", fontSize=8, textColor=WHITE, spaceAfter=0)),
        Paragraph("<b>Key Metric</b>",sty("Normal", fontSize=8, textColor=WHITE, spaceAfter=0)),
    ]
    ov_data = [ov_hdr]
    ov_ts   = [
        ("BACKGROUND",    (0,0), (-1,0), NAVY),
        ("FONTSIZE",      (0,0), (-1,-1), 8),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [WHITE, LGREY]),
        ("GRID",          (0,0), (-1,-1), 0.4, MGREY),
        ("PADDING",       (0,0), (-1,-1), 6),
        ("VALIGN",        (0,0), (-1,-1), "TOP"),
    ]

    for i, r in enumerate(sorted_loops, start=1):
        sev      = str(getattr(r, "Severity", "OK"))
        health_v = fmt(r._4, 0)
        diag_v   = str(r.Diagnosis) if str(r.Diagnosis) != "nan" else "—"
        harris_v = fmt(getattr(r, "Harris_Index", r._12 if hasattr(r,"_12") else "—"), 2)
        iae_v    = fmt(r._7 if hasattr(r,"_7") else "—", 0)
        key_met  = f"Harris: {harris_v}  |  IAE/hr: {iae_v}"
        sc = sev_color(sev)
        ov_data.append([
            Paragraph(str(r.Loop), MONO_CELL),
            Paragraph(f"<b>{sev}</b>", sty("Normal", fontSize=8, textColor=sc, fontName="Helvetica-Bold", spaceAfter=0)),
            Paragraph(f"<b>{health_v}</b>", sty("Normal", fontSize=8, textColor=sc, fontName="Helvetica-Bold", spaceAfter=0)),
            Paragraph(diag_v, CELL),
            Paragraph(key_met, sty("Normal", fontSize=7, textColor=DGREY, spaceAfter=0)),
        ])
        ov_ts.append(("BACKGROUND", (1,i), (2,i), sev_bg(sev)))

    ov_tbl = Table(ov_data, colWidths=[4.2*cm, 1.6*cm, 1.4*cm, 5.6*cm, 4.2*cm])
    ov_tbl.setStyle(TableStyle(ov_ts))
    story.append(ov_tbl)

    # ══ SECTION 3: PER-LOOP DETAILED ANALYSIS ════════════════════════════════
    story.append(PageBreak())
    story.append(Paragraph("3. Detailed Loop Analysis", H2))
    story.append(Paragraph(
        "Each loop is presented with its full diagnostic breakdown, key performance "
        "metrics, root-cause explanation, and recommended corrective action.", BODY))

    for r in sorted_loops:
        loop      = str(r.Loop)
        diag      = str(r.Diagnosis) if str(r.Diagnosis) != "nan" else "No fault detected"
        sev       = str(getattr(r, "Severity", "OK"))
        health_v  = fmt(r._4, 0)
        conf      = fmt(getattr(r, "Confidence", r._5 if hasattr(r,"_5") else "—"), 0)
        sf        = fmt(r._6  if hasattr(r,"_6")  else "—", 1)
        iae       = fmt(r._7  if hasattr(r,"_7")  else "—", 1)
        harris    = fmt(r._12 if hasattr(r,"_12") else "—", 3)
        op_act    = fmt(r._9  if hasattr(r,"_9")  else "—", 2)
        action    = str(r._22 if hasattr(r,"_22") else "—")
        rationale = str(r.Rationale) if hasattr(r, "Rationale") and str(r.Rationale) != "nan" else ""
        detail    = str(r._24 if hasattr(r,"_24") else "")
        if detail in ("nan", "None"): detail = ""

        sc  = sev_color(sev)
        sb  = sev_bg(sev)

        story.append(Spacer(1, 0.3*cm))

        # ── Loop header banner — always navy, severity as badge ───────────────
        sev_badge_color = "#e57373" if str(sev).upper() in ("FAIL","CRITICAL") else \
                          "#ffcc80" if str(sev).upper() in ("WARN","WARNING") else "#81c995"
        hdr_data = [[
            Paragraph(f"<font color='#ffffff'><b>{loop}</b></font>",
                      sty("Normal", fontSize=11, fontName="Helvetica-Bold", spaceAfter=0)),
            Paragraph(f"<font color='#a8c8f0'>{diag}</font>",
                      sty("Normal", fontSize=9, spaceAfter=0)),
            Paragraph(f"<font color='{sev_badge_color}'><b>{sev}</b></font>",
                      sty("Normal", fontSize=9, fontName="Helvetica-Bold", spaceAfter=0, alignment=2)),
        ]]
        hdr_tbl = Table(hdr_data, colWidths=[4.5*cm, 9.5*cm, 3*cm])
        hdr_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,-1), NAVY),
            ("PADDING",    (0,0), (-1,-1), 9),
            ("VALIGN",     (0,0), (-1,-1), "MIDDLE"),
        ]))
        story.append(hdr_tbl)

        # ── Severity + health strip — plain light grey ───────────────────────
        sev_strip_data = [[
            Paragraph(f"Severity: <b><font color='#{to_hex(sc)}'>{sev}</font></b>",
                      sty("Normal", fontSize=8, textColor=NAVY, spaceAfter=0)),
            Paragraph(f"Health Score: <b>{health_v}/100</b>",
                      sty("Normal", fontSize=8, textColor=NAVY, spaceAfter=0)),
            Paragraph(f"Confidence: <b>{conf}%</b>",
                      sty("Normal", fontSize=8, textColor=NAVY, spaceAfter=0)),
        ]]
        sev_strip = Table(sev_strip_data, colWidths=[4*cm, 5*cm, 5*cm])
        sev_strip.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,-1), LGREY),
            ("PADDING",    (0,0), (-1,-1), 6),
            ("VALIGN",     (0,0), (-1,-1), "MIDDLE"),
            ("GRID",       (0,0), (-1,-1), 0.4, MGREY),
        ]))
        story.append(sev_strip)

        # ── Metrics grid ──────────────────────────────────────────────────────
        def metric_cell(label, val, unit=""):
            return [
                Paragraph(label, sty("Normal", fontSize=7, textColor=DGREY, spaceAfter=0)),
                Paragraph(f"<b>{val}{unit}</b>", sty("Normal", fontSize=10, textColor=NAVY, fontName="Helvetica-Bold", spaceAfter=0)),
            ]

        m_data = [
            [Paragraph("Service\nFactor", sty("Normal", fontSize=7, textColor=DGREY, spaceAfter=0)),
             Paragraph("Harris\nIndex",   sty("Normal", fontSize=7, textColor=DGREY, spaceAfter=0)),
             Paragraph("IAE / hr",        sty("Normal", fontSize=7, textColor=DGREY, spaceAfter=0)),
             Paragraph("OP Activity",     sty("Normal", fontSize=7, textColor=DGREY, spaceAfter=0))],
            [Paragraph(f"<b>{sf}%</b>",   sty("Normal", fontSize=12, textColor=NAVY, fontName="Helvetica-Bold", spaceAfter=0)),
             Paragraph(f"<b>{harris}</b>",sty("Normal", fontSize=12, textColor=NAVY, fontName="Helvetica-Bold", spaceAfter=0)),
             Paragraph(f"<b>{iae}</b>",   sty("Normal", fontSize=12, textColor=NAVY, fontName="Helvetica-Bold", spaceAfter=0)),
             Paragraph(f"<b>{op_act}</b>",sty("Normal", fontSize=12, textColor=NAVY, fontName="Helvetica-Bold", spaceAfter=0))],
        ]
        m_tbl = Table(m_data, colWidths=[4.25*cm]*4)
        m_tbl.setStyle(TableStyle([
            ("BACKGROUND",    (0,0), (-1,-1), LGREY),
            ("GRID",          (0,0), (-1,-1), 0.4, MGREY),
            ("PADDING",       (0,0), (-1,-1), 7),
            ("ALIGN",         (0,0), (-1,-1), "CENTER"),
            ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        ]))
        story.append(m_tbl)

        # ── Summary ───────────────────────────────────────────────────────────
        if rationale:
            summary_data = [[
                Paragraph("📋 SUMMARY", sty("Normal", fontSize=7, textColor=DGREY, fontName="Helvetica-Bold", spaceAfter=2)),
            ],[
                Paragraph(rationale, BODY),
            ]]
            summary_tbl = Table(summary_data, colWidths=[17*cm])
            summary_tbl.setStyle(TableStyle([
                ("BACKGROUND", (0,0), (-1,-1), colors.HexColor("#f8fafc")),
                ("PADDING",    (0,0), (-1,-1), 8),
                ("LINEABOVE",  (0,0), (-1,0),  0.5, BLUE),
            ]))
            story.append(summary_tbl)

        # ── Detail explanation ────────────────────────────────────────────────
        if detail:
            detail_clean = (detail
                .replace("\\n\\n", "\n\n")
                .replace("\\n", " ")
                .replace("\n\n", "<br/><br/>")
                .replace("\n", " "))
            # Split into labelled sections (FINDING / ANALYSIS / CONCLUSION / etc.)
            sections = re.split(r'(FINDING:|ANALYSIS:|CONCLUSION:|IMPACT:|Oscillation Analysis\]|Performance Metrics\]|Controller Output\]|Process Variable\])', detail_clean)
            detail_rows = []
            i_s = 0
            while i_s < len(sections):
                chunk = sections[i_s].strip()
                if not chunk:
                    i_s += 1; continue
                if chunk.endswith(":") or chunk.endswith("]"):
                    label = chunk.lstrip("[")
                    body_chunk = sections[i_s+1].strip() if i_s+1 < len(sections) else ""
                    detail_rows.append([
                        Paragraph(f"<b>{label}</b>", sty("Normal", fontSize=7, textColor=BLUE, fontName="Helvetica-Bold", spaceAfter=0)),
                        Paragraph(body_chunk, BODY),
                    ])
                    i_s += 2
                else:
                    detail_rows.append(["", Paragraph(chunk, BODY)])
                    i_s += 1

            if detail_rows:
                det_tbl = Table(detail_rows, colWidths=[3*cm, 14*cm])
                det_tbl.setStyle(TableStyle([
                    ("BACKGROUND",   (0,0), (-1,-1), WHITE),
                    ("BACKGROUND",   (0,0), (0,-1), LGREY),
                    ("PADDING",      (0,0), (-1,-1), 6),
                    ("GRID",         (0,0), (-1,-1), 0.3, MGREY),
                    ("VALIGN",       (0,0), (-1,-1), "TOP"),
                    ("FONTSIZE",     (0,0), (-1,-1), 8),
                ]))
                story.append(det_tbl)

        # ── Recommended action ────────────────────────────────────────────────
        if action and action not in ("nan", "—", "None"):
            act_data = [[
                Paragraph("🔧 RECOMMENDED ACTION",
                          sty("Normal", fontSize=7, textColor=DGREY, fontName="Helvetica-Bold", spaceAfter=3)),
            ],[
                Paragraph(action, sty("Normal", fontSize=9, textColor=NAVY, leading=14, spaceAfter=0)),
            ]]
            act_tbl = Table(act_data, colWidths=[17*cm])
            act_tbl.setStyle(TableStyle([
                ("BACKGROUND",  (0,0), (-1,-1), colors.HexColor("#f8fafc")),
                ("PADDING",     (0,0), (-1,-1), 10),
                ("LINEBEFORE",  (0,0), (0,-1),  3, sc),
                ("LINEABOVE",   (0,0), (-1,0),   0.4, MGREY),
                ("LINEBELOW",   (0,-1),(-1,-1),  0.4, MGREY),
            ]))
            story.append(act_tbl)

        # ── Loop trend plot ───────────────────────────────────────────────────
        from reportlab.platypus import Image as RLImage
        plot_path = rd_path / "plots" / f"{loop}.png"
        if plot_path.exists():
            story.append(Spacer(1, 0.3*cm))
            trend_hdr = Table([[Paragraph(
                "📈 LOOP TREND (PV / SP / OP)",
                sty("Normal", fontSize=7, textColor=DGREY, fontName="Helvetica-Bold", spaceAfter=0)
            )]], colWidths=[17*cm])
            trend_hdr.setStyle(TableStyle([
                ("BACKGROUND", (0,0), (-1,-1), LGREY),
                ("PADDING",    (0,0), (-1,-1), 6),
                ("LINEABOVE",  (0,0), (-1,0),  0.4, MGREY),
            ]))
            story.append(trend_hdr)
            story.append(Spacer(1, 0.15*cm))
            try:
                story.append(RLImage(str(plot_path), width=17*cm, height=8*cm))
            except Exception:
                story.append(Paragraph("<i>[Trend plot could not be embedded]</i>",
                    sty("Normal", fontSize=8, textColor=DGREY, spaceAfter=0)))
            story.append(Spacer(1, 0.2*cm))

    # ══ SECTION 4: OUTLIER HANDLING ═══════════════════════════════════════════
    story.append(PageBreak())
    story.append(Paragraph("4. Data Quality — Outlier Handling", H2))
    story.append(Paragraph(
        "This section summarises how the tool handled anomalous or physically impossible "
        "values in the input data before running diagnostics. The original file was not modified.", BODY))
    story.append(Spacer(1, 0.2*cm))

    if outlier_text:
        for line in outlier_text.splitlines():
            line = line.strip()
            if not line:
                story.append(Spacer(1, 0.15*cm))
            elif any(line.startswith(k) for k in ("REMOVED", "FLAGGED")):
                story.append(Paragraph(line, sty("Normal", fontSize=9, textColor=CRIT, fontName="Helvetica-Bold")))
            elif any(k in line for k in ("KEPT", "No outliers")):
                story.append(Paragraph(line, sty("Normal", fontSize=9, textColor=OK, fontName="Helvetica-Bold")))
            elif any(line.startswith(k) for k in ("PRINCIPLES", "WHAT WE")):
                story.append(Paragraph(line, sty("Normal", fontSize=9, textColor=NAVY, fontName="Helvetica-Bold")))
            else:
                story.append(Paragraph(line, BODY))
    else:
        ok_box = Table([[Paragraph("✔  No outliers detected — input data was clean.", sty("Normal", fontSize=9, textColor=OK, fontName="Helvetica-Bold", spaceAfter=0))]],
                       colWidths=[17*cm])
        ok_box.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),OK_BG),("PADDING",(0,0),(-1,-1),10)]))
        story.append(ok_box)

    # ══ INTERPRETATION GUIDE ══════════════════════════════════════════════════
    story.append(PageBreak())
    story.append(Paragraph("5. Interpretation Guide", H2))
    story.append(Paragraph("Plain-language explanation of every metric used in this report.", BODY))
    story.append(Spacer(1, 0.2*cm))

    notes = [
        ("Plant Health Index", "0–100 plant-wide score. ≥75 = Good. 50–74 = Needs attention. <50 = Critical."),
        ("Health Score (loop)", "0–100 per-loop score. 100 = no faults. Drops based on severity and confidence of detected faults."),
        ("Harris Index", "Control performance vs minimum achievable variance. <0.3 = poor. 0.3–0.7 = acceptable. >0.7 = good."),
        ("IAE / hr", "Integral Absolute Error per hour. How much PV deviates from SP over time. Lower is better."),
        ("Service Factor", "% of time the loop was in AUTO mode. <70% may indicate excessive manual intervention."),
        ("OP Activity", "Mean absolute change in controller output per sample. High values indicate oscillation or aggressive tuning."),
        ("Stiction", "Mechanical friction causing the valve to stick then jump. Diagnosed from the PV-OP relationship shape."),
        ("Saturation", "Valve at its physical limit (fully open/closed) and unable to respond further to controller demands."),
        ("Aggressive Tuning", "Controller gains too high, causing oscillation. PV and OP oscillate together with regularity >0.6."),
        ("Hägglund Regularity", "Measures how regular (periodic) the oscillation is. >0.6 = sustained oscillation."),
    ]
    note_hdr = [[
        Paragraph("<b>Metric</b>",      sty("Normal", fontSize=8, textColor=WHITE, spaceAfter=0)),
        Paragraph("<b>Explanation</b>", sty("Normal", fontSize=8, textColor=WHITE, spaceAfter=0)),
    ]]
    note_rows = note_hdr + [
        [Paragraph(f"<b>{t}</b>", sty("Normal", fontSize=8, textColor=NAVY, fontName="Helvetica-Bold", spaceAfter=0)),
         Paragraph(e, CELL)]
        for t, e in notes
    ]
    note_tbl = Table(note_rows, colWidths=[4.5*cm, 12.5*cm])
    note_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0), NAVY),
        ("TEXTCOLOR",     (0,0), (-1,0), WHITE),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [WHITE, LGREY]),
        ("GRID",          (0,0), (-1,-1), 0.4, MGREY),
        ("PADDING",       (0,0), (-1,-1), 7),
        ("VALIGN",        (0,0), (-1,-1), "TOP"),
        ("FONTSIZE",      (0,0), (-1,-1), 8),
    ]))
    story.append(note_tbl)

    # ── Build ─────────────────────────────────────────────────────────────────
    doc.build(story)
    buf.seek(0)

    # ── Package PDF + Excel into a single zip ────────────────────────────────
    import zipfile
    ts      = datetime.now().strftime('%Y%m%d_%H%M')
    pdf_name = f"Valve_Diagnostic_Report_{ts}.pdf"
    zip_buf  = io.BytesIO()

    with zipfile.ZipFile(zip_buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Add the PDF we just built
        zf.writestr(pdf_name, buf.getvalue())
        # Add the Excel from results folder
        if xl_path.exists():
            zf.write(xl_path, f"Loop_diagnostics_v2_{ts}.xlsx")

    zip_buf.seek(0)
    zip_name = f"Valve_Diagnostics_{ts}.zip"
    return StreamingResponse(
        zip_buf,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={zip_name}"}
    )




@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code == 401:
        return RedirectResponse(url="/login", status_code=302)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)