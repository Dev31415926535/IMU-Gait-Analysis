# backend/server.py
import os, json, uuid, csv, re, shutil, subprocess
from datetime import datetime
from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse

# -------------------------------------------------------
# Paths (same as before)
# -------------------------------------------------------
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(ROOT_DIR, "data")
RECORDING_DIR = os.path.join(DATA_DIR, "recordings")
PATIENT_FILE = os.path.join(DATA_DIR, "patients.json")
RECORDING_FILE = os.path.join(DATA_DIR, "recordings.json")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(RECORDING_DIR, exist_ok=True)

app = FastAPI()

# -------------------------------------------------------
# CORS
# -------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# -------------------------------------------------------
# Helpers
# -------------------------------------------------------
def load_json(path):
    if not os.path.exists(path): return []
    with open(path, "r") as f:
        try: return json.load(f)
        except: return []

def save_json(path, data):
    with open(path, "w") as f: json.dump(data, f, indent=2)

def slugify(name: str):
    s = name.lower().strip()
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"[^a-z0-9_\-]", "", s)
    return s[:60]

# -------------------------------------------------------
# NEW: Find latest bilateral recording for a patient
# -------------------------------------------------------
def find_latest_bilateral(patient_id: str, patient_name: str):
    patient_dir = os.path.join(RECORDING_DIR, patient_name)
    if not os.path.exists(patient_dir):
        return None, None

    all_runs = []

    for root, dirs, files in os.walk(patient_dir):
        for file in files:
            if file.endswith(".csv") and "bilateral_angles" in file:
                full_path = os.path.join(root, file)
                all_runs.append(full_path)

    if not all_runs:
        return None, None

    all_runs.sort(key=os.path.getmtime, reverse=True)
    latest_csv = all_runs[0]

    # Try finding raw json in the same folder
    folder = os.path.dirname(latest_csv)
    json_files = [
        f for f in os.listdir(folder)
        if f.startswith("bilateral_raw") and f.endswith(".json")
    ]
    latest_json = os.path.join(folder, json_files[0]) if json_files else None

    return latest_json, latest_csv

# -------------------------------------------------------
# /analyze — run src/main_bilateral.py and save recording
# -------------------------------------------------------
@app.post("/analyze")
async def analyze(req: Request):
    data = await req.json()
    patient_id = data.get("patient_id")
    name = data.get("name", "unknown")

    if not patient_id:
        raise HTTPException(status_code=400, detail="Missing patient_id")

    script_path = os.path.join(ROOT_DIR, "src/main_bilateral.py")

    def stream_output():
        process = subprocess.Popen(
            # ["python3", script_path, patient_id, name],
            ["python", "-u", script_path, patient_id, name],
            cwd=ROOT_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        for line in iter(process.stdout.readline, ""):
            yield line

        process.stdout.close()
        process.wait()

        # Save final CSV → metadata
        raw_f, csv_f = find_latest_bilateral(patient_id, name)
        if csv_f:
            timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")

            save_json(RECORDING_FILE, load_json(RECORDING_FILE) + [{
                "patient_id": patient_id,
                "name": name,
                "csv": csv_f,
                "raw": raw_f,
                "timestamp": timestamp
            }])

            yield f"\n🎉 Saved bilateral recording: {csv_f}\n"
        else:
            yield "\n⚠️ No CSV found.\n"

    return StreamingResponse(stream_output(), media_type="text/plain")

# -------------------------------------------------------
# /recordings — returns all bilateral recordings
# -------------------------------------------------------
@app.get("/recordings")
def list_recordings(patient_id: str = Query(...), patient_name: str = Query(...)):
    patient_dir = os.path.join(RECORDING_DIR, patient_name)
    if not os.path.exists(patient_dir):
        return []

    out = []

    for root, dirs, files in os.walk(patient_dir):
        metrics_file = None
        report_file = None

        for f in files:
            if f.startswith("bilateral_metrics") and f.endswith(".json"):
                metrics_file = os.path.join(root, f)
            if f.startswith("bilateral_gait_report") and f.endswith(".json"):
                report_file = os.path.join(root, f)

        if metrics_file:
            session_id = os.path.basename(root) + "_" + os.path.basename(metrics_file).replace(".json","")
            out.append({
                "id": session_id,
                "label": os.path.basename(root),
                "metrics_file": metrics_file,
                "report_file": report_file
            })

    out.sort(key=lambda x: os.path.getmtime(x["metrics_file"]), reverse=True)
    return out

# -------------------------------------------------------
# /recordings/{id} — parse json
# -------------------------------------------------------

# @app.get("/recordings/{rid}")
# def get_recording(rid: str, patient_name: str = Query(...)):
#     patient_dir = os.path.join(RECORDING_DIR, patient_name)

#     if not os.path.exists(patient_dir):
#         raise HTTPException(status_code=404, detail="Patient folder not found")

#     # Extract the actual filename: everything after the first "_"
#     # rid example: "2025-11-15_10-52-57_bilateral_metrics_20251115_105405"
#     # filename prefix:   "bilateral_metrics_20251115_105405"
#     filename_prefix = "_".join(rid.split("_")[2:])

#     target_file = None

#     for root, dirs, files in os.walk(patient_dir):
#         for f in files:
#             if f.startswith(filename_prefix) and f.endswith(".json"):
#                 target_file = os.path.join(root, f)
#                 break

#     if not target_file:
#         raise HTTPException(status_code=404, detail="Recording not found")

#     try:
#         with open(target_file) as f:
#             data = json.load(f)
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"JSON parse error: {str(e)}")

#     return {
#         "id": rid,
#         "label": rid,
#         "data": data
#     }

@app.get("/recordings/{rid}")
def get_recording(rid: str, patient_name: str = Query(...)):
    patient_dir = os.path.join(RECORDING_DIR, patient_name)

    if not os.path.exists(patient_dir):
        raise HTTPException(status_code=404, detail="Patient folder not found")

    # Extract timestamp (last two parts)
    # Example rid:
    #   2025-11-19_22-22-05_bilateral_metrics_20251119_222205
    # Extract => "20251119_222205"
    parts = rid.split("_")
    timestamp = "_".join(parts[-2:])   # last two: YYYYMMDD + HHMMSS

    metrics_file = None
    report_file = None

    # Search all files matching the same timestamp
    for root, dirs, files in os.walk(patient_dir):
        for f in files:
            if f.endswith(".json") and timestamp in f:
                full = os.path.join(root, f)
                if "metrics" in f:
                    metrics_file = full
                elif "gait_report" in f:
                    report_file = full

    if not metrics_file:
        raise HTTPException(status_code=404, detail="Metrics file not found")

    # Load metrics
    try:
        with open(metrics_file, "r") as f:
            metrics_data = json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Metrics JSON parse error: {str(e)}")

    # Load report (optional)
    report_data = None
    if report_file:
        try:
            with open(report_file, "r") as f:
                report_data = json.load(f)
        except:
            report_data = None

    return {
        "id": rid,
        "angles": metrics_data,
        "report": report_data
    }




# -------------------------------------------------------
# Patients + Users (unchanged)
# -------------------------------------------------------
@app.get("/users")
def get_users():
    patients = load_json(PATIENT_FILE)
    return [
        {
            "username": slugify(p["name"]),
            "role": p.get("role", "patient"),
            "patientId": p["id"],
        }
        for p in patients
    ]

@app.get("/patients")
def get_patients():
    return load_json(PATIENT_FILE)

# @app.get("/patients/{pid}")
# def get_patient(pid: str):
#     patients = load_json(PATIENT_FILE)
#     patient = next((p for p in patients if p["id"] == pid), None)
#     if not patient:
#         raise HTTPException(status_code=404, detail="Patient not found")
#     # patient["recordings"] = [
#     #     r for r in load_json(RECORDING_FILE)
#     #     if r.get("patient_id") == pid
#     # ]
#     recs = [
#         r for r in load_json(RECORDING_FILE)
#         if r.get("patient_id") == pid
#     ]

#     # Sort newest → oldest
#     recs.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

#     patient["recordings"] = recs

#     return patient
@app.get("/patients/{pid}")
def get_patient(pid: str):
    patients = load_json(PATIENT_FILE)
    patient = next((p for p in patients if p["id"] == pid), None)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    # Load all recordings for this patient
    recs = [
        r for r in load_json(RECORDING_FILE)
        if r.get("patient_id") == pid
    ]

    # Sort newest → oldest
    recs.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

    # Inject recording id (required by frontend)
    # Example id = "2025-11-15_10-52-57_bilateral_metrics_20251115_105405"
    formatted = []
    for r in recs:
        csv_name = os.path.basename(r.get("csv", ""))
        # remove .csv and use as id
        rec_id = csv_name.replace(".csv", "") if csv_name else None

        formatted.append({
            "id": rec_id,
            "timestamp": r.get("timestamp"),
            "csv": r.get("csv"),
            "raw": r.get("raw")
        })

    patient["recordings"] = formatted
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
