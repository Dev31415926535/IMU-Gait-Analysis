# from fastapi import FastAPI, HTTPException
# from fastapi.middleware.cors import CORSMiddleware
# import json, os, subprocess, time

# DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data'))
# PATIENT_FILE = os.path.join(DATA_DIR, 'patients.json')
# RECORDING_DIR = os.path.join(DATA_DIR, 'recordings')

# app = FastAPI()

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# def load_patients():
#     with open(PATIENT_FILE, 'r') as f:
#         return json.load(f)

# def save_patients(patients):
#     with open(PATIENT_FILE, 'w') as f:
#         json.dump(patients, f, indent=2)

# @app.get("/patients")
# def get_patients():
#     return load_patients()

# @app.get("/patients/{pid}")
# def get_patient(pid: str):
#     patients = load_patients()
#     patient = next((p for p in patients if p["id"] == pid), None)
#     if not patient:
#         raise HTTPException(status_code=404, detail="Patient not found")
#     return patient

# @app.post("/patients")
# def create_patient(payload: dict):
#     patients = load_patients()
#     new_patient = {"id": str(int(time.time())), **payload}
#     patients.append(new_patient)
#     save_patients(patients)
#     return new_patient

# @app.put("/patients/{pid}")
# def update_patient(pid: str, payload: dict):
#     patients = load_patients()
#     for p in patients:
#         if p["id"] == pid:
#             p.update(payload)
#             save_patients(patients)
#             return p
#     raise HTTPException(status_code=404, detail="Patient not found")

# @app.delete("/patients/{pid}")
# def delete_patient(pid: str):
#     patients = load_patients()
#     new_patients = [p for p in patients if p["id"] != pid]
#     save_patients(new_patients)
#     return {"ok": True}

# @app.post("/analyze/{pid}")
# def analyze_patient(pid: str):
#     """
#     Runs your backend/src/main.py to collect 30s data and returns summary metrics.
#     """
#     print(f"Starting analysis for patient {pid}...")
#     try:
#         # Run analysis script (blocks for ~30s)
#         result = subprocess.run(
#             ["python", "src/main.py"],
#             cwd=os.path.join(os.path.dirname(__file__), ".."),
#             capture_output=True, text=True, timeout=60
#         )
#         if result.returncode != 0:
#             raise Exception(result.stderr)
#     except subprocess.TimeoutExpired:
#         raise HTTPException(status_code=500, detail="Analysis timeout")

#     # After analysis, find the latest metrics JSON or CSV (mock response)
#     files = sorted(os.listdir(RECORDING_DIR))
#     latest = files[-1] if files else None
#     return {"patient_id": pid, "status": "completed", "file": latest}

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import json, os, subprocess, time, uuid

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
PATIENT_FILE = os.path.join(DATA_DIR, 'patients.json')
RECORDING_FILE = os.path.join(DATA_DIR, 'recordings.json')
RECORDING_DIR = os.path.join(DATA_DIR, 'recordings')

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def load_json(path):
    if not os.path.exists(path): return []
    with open(path, 'r') as f:
        return json.load(f)

def save_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)

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

    # also attach that patient's recordings
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

@app.post("/analyze/{pid}")
def analyze_patient(pid: str):
    """Runs main.py and stores a new recording for that patient"""
    patients = load_json(PATIENT_FILE)
    if not any(p["id"] == pid for p in patients):
        raise HTTPException(status_code=404, detail="Patient not found")

    print(f"Starting analysis for patient {pid}...")
    try:
        result = subprocess.run(
            ["python", "src/main.py"],
            cwd=os.path.join(os.path.dirname(__file__), ".."),
            capture_output=True, text=True, timeout=60
        )
        if result.returncode != 0:
            raise Exception(result.stderr)
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail="Analysis timeout")

    ts = int(time.time())
    rec_id = f"r{ts}"
    new_rec = {
        "id": rec_id,
        "patient_id": pid,
        "date": time.strftime("%Y-%m-%d"),
        "file": f"raw_{ts}.jsonl",
        "metrics": {"mean_knee_angle_deg": 50 + ts % 5}  # mock metric
    }

    recs = load_json(RECORDING_FILE)
    recs.append(new_rec)
    save_json(RECORDING_FILE, recs)

    return {"status": "completed", "recording": new_rec}