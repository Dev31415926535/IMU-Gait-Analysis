



from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
import json, os, subprocess, time, uuid, shutil, re

# Project root is one level up from this file (backend/)
DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data'))
PATIENT_FILE = os.path.join(DATA_DIR, 'patients.json')
RECORDING_FILE = os.path.join(DATA_DIR, 'recordings.json')
RECORDING_DIR = os.path.join(DATA_DIR, 'recordings')

os.makedirs(RECORDING_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def load_json(path):
    if not os.path.exists(path):
        return []
    with open(path, 'r') as f:
        try:
            return json.load(f)
        except Exception:
            return []

def save_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)

def slugify(name: str):
    # simple slugify - lower, replace spaces with _, remove non-alnum/_/-
    s = name.lower().strip()
    s = re.sub(r'\s+', '_', s)
    s = re.sub(r'[^a-z0-9_\-]', '', s)
    return s[:60]  # keep reasonably short

def find_latest_raw_and_csv():
    # find latest raw_*.jsonl in RECORDING_DIR by mtime
    raw_files = [f for f in os.listdir(RECORDING_DIR) if f.startswith("raw_") and f.endswith(".jsonl")]
    raw_files = sorted(raw_files, key=lambda fn: os.path.getmtime(os.path.join(RECORDING_DIR, fn))) if raw_files else []
    latest_raw = raw_files[-1] if raw_files else None

    # CSV may be written as 'joint_angles.csv' or a time-based name; pick newest .csv
    csv_files = [f for f in os.listdir(RECORDING_DIR) if f.endswith(".csv")]
    csv_files = sorted(csv_files, key=lambda fn: os.path.getmtime(os.path.join(RECORDING_DIR, fn))) if csv_files else []
    latest_csv = csv_files[-1] if csv_files else None

    return latest_raw, latest_csv

# ---------- PATIENT ROUTES ----------
@app.get("/patients")
def get_patients():
    return load_json(PATIENT_FILE)

@app.get("/patients/{pid}")
def get_patient(pid: str):
    patients = load_json(PATIENT_FILE)
    patient = next((p for p in patients if p["id"] == pid), None)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    recs = [r for r in load_json(RECORDING_FILE) if r["patient_id"] == pid]
    patient["recordings"] = recs
    return patient

@app.post("/patients")
def create_patient(payload: dict):
    patients = load_json(PATIENT_FILE)
    new_patient = {"id": str(uuid.uuid4()), **payload}
    patients.append(new_patient)
    save_json(PATIENT_FILE, patients)
    return new_patient

@app.put("/patients/{pid}")
def update_patient(pid: str, payload: dict):
    patients = load_json(PATIENT_FILE)
    for p in patients:
        if p["id"] == pid:
            p.update(payload)
            save_json(PATIENT_FILE, patients)
            return p
    raise HTTPException(status_code=404, detail="Patient not found")

@app.delete("/patients/{pid}")
def delete_patient(pid: str):
    patients = [p for p in load_json(PATIENT_FILE) if p["id"] != pid]
    save_json(PATIENT_FILE, patients)
    return {"ok": True}

# ---------- RECORDINGS ----------
@app.get("/recordings/{rid}")
def get_recording(rid: str):
    recs = load_json(RECORDING_FILE)
    rec = next((r for r in recs if r["id"] == rid), None)
    if not rec:
        raise HTTPException(status_code=404, detail="Recording not found")
    return rec

@app.post("/analyze")
async def analyze_patient(request: Request):
    body = await request.json()
    pid = body.get("patientId") or body.get("patient_id")
    custom_label = body.get("label")
    mock = bool(body.get("mock", False))
    if not pid:
        raise HTTPException(status_code=400, detail="Missing patientId in request body")

    patients = load_json(PATIENT_FILE)
    patient = next((p for p in patients if p["id"] == pid), None)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    patient_name = patient.get("name", "patient")
    slug = slugify(patient_name)
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    print(f"Starting analysis for patient {pid} (name={patient_name}) in {project_root} ...")

    # MOCK mode: create fake files so you can test frontend without ESP32
    if mock:
        ts = int(time.time())
        date_str = time.strftime("%Y-%m-%d")
        raw_name = f"{slug}_{date_str}_{ts}_raw.jsonl"
        angles_name = f"{slug}_{date_str}_{ts}_angles.csv"
        # create small fake files
        with open(os.path.join(RECORDING_DIR, raw_name), "w") as f:
            f.write(json.dumps({"fake": True, "ts": ts}) + "\n")
        with open(os.path.join(RECORDING_DIR, angles_name), "w") as f:
            f.write("time_s,angle_deg\n0.0,10\n0.1,11\n")
        rec_id = f"r{ts}_{uuid.uuid4().hex[:6]}"
        rec = {
            "id": rec_id,
            "patient_id": pid,
            "date": date_str,
            "timestamp": ts,
            "label": custom_label or f"{patient_name} {date_str}",
            "raw_file": raw_name,
            "angles_file": angles_name,
            "metrics": {"mock": True}
        }
        recs = load_json(RECORDING_FILE); recs.append(rec); save_json(RECORDING_FILE, recs)
        return {"status": "completed", "recording": rec}

    # Real run: set AUTO_START so main.py won't wait for input
    env = os.environ.copy()
    env["AUTO_START"] = "1"
    # optionally pass patient info or duration via env if main.py supports it
    # env["PATIENT_ID"] = pid

    try:
        result = subprocess.run(
            ["python", "src/main.py"],
            cwd=project_root,
            capture_output=True,
            text=True,
            env=env,
            timeout=180  # give it more time in case initial processing takes a bit
        )
        if result.returncode != 0:
            # include stdout/stderr in error for debugging (dev only)
            detail = {
                "msg": "main.py failed",
                "returncode": result.returncode,
                "stdout": result.stdout[-2000:],   # limit size
                "stderr": result.stderr[-2000:]
            }
            print("main.py failure detail:", detail)
            raise Exception(json.dumps(detail))
    except subprocess.TimeoutExpired as e:
        print("main.py timeout:", str(e))
        raise HTTPException(status_code=500, detail="Analysis timeout")
    except Exception as e:
        # if we got an exception constructing the error, return some info for dev debugging
        err = str(e)
        print("Analysis exception:", err)
        raise HTTPException(status_code=500, detail=f"Analysis failed: {err}")

    # find output files (same logic as before)
    latest_raw, latest_csv = find_latest_raw_and_csv()
    if latest_raw is None and latest_csv is None:
        raise HTTPException(status_code=500, detail="No output files produced by analysis")

    ts = int(time.time()); date_str = time.strftime("%Y-%m-%d"); safe_ts = str(ts)
    new_raw_name = None; new_csv_name = None

    if latest_raw:
        src_raw = os.path.join(RECORDING_DIR, latest_raw)
        new_raw_name = f"{slug}_{date_str}_{safe_ts}_raw.jsonl"
        shutil.copy(src_raw, os.path.join(RECORDING_DIR, new_raw_name))

    if latest_csv:
        src_csv = os.path.join(RECORDING_DIR, latest_csv)
        new_csv_name = f"{slug}_{date_str}_{safe_ts}_angles.csv"
        try:
            shutil.copy(src_csv, os.path.join(RECORDING_DIR, new_csv_name))
        except Exception as e:
            print("Failed to copy csv:", e)
            new_csv_name = None

    rec_id = f"r{int(time.time())}_{uuid.uuid4().hex[:6]}"
    rec_label = custom_label or f"{patient_name} {date_str}"
    new_rec = {
        "id": rec_id,
        "patient_id": pid,
        "date": date_str,
        "timestamp": ts,
        "label": rec_label,
        "raw_file": new_raw_name,
        "angles_file": new_csv_name,
        "metrics": {}
    }

    # attempt parse JSON metrics from stdout (if main.py prints metrics JSON)
    try:
        out_lines = [ln.strip() for ln in result.stdout.splitlines() if ln.strip()]
        if out_lines:
            last = out_lines[-1]
            parsed = json.loads(last)
            if isinstance(parsed, dict):
                new_rec["metrics"] = parsed
    except Exception:
        pass

    recs = load_json(RECORDING_FILE)
    recs.append(new_rec)
    save_json(RECORDING_FILE, recs)

    return {"status": "completed", "recording": new_rec}
