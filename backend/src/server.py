# backend/server.py
from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
import os, json, uuid, shutil, re, asyncio, csv
from datetime import datetime

# ---------- Paths ----------
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(ROOT_DIR, "data")
RECORDING_DIR = os.path.join(DATA_DIR, "recordings")
PATIENT_FILE = os.path.join(DATA_DIR, "patients.json")
RECORDING_FILE = os.path.join(DATA_DIR, "recordings.json")

os.makedirs(RECORDING_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

# ---------- App ----------
app = FastAPI()

# ---------- CORS ----------
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

# ---------- Helpers ----------
def load_json(path):
    """Load JSON from file safely."""
    if not os.path.exists(path):
        return []
    with open(path, "r") as f:
        try:
            return json.load(f)
        except Exception:
            return []

def save_json(path, data):
    """Save JSON with indentation."""
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def slugify(name: str):
    """Convert a string into a safe filename."""
    s = name.lower().strip()
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"[^a-z0-9_\-]", "", s)
    return s[:60]

def find_latest_raw_and_csv():
    """Find latest raw JSONL and CSV files."""
    try:
        raw_files = [f for f in os.listdir(RECORDING_DIR) if f.startswith("raw_") and f.endswith(".jsonl")]
        csv_files = [f for f in os.listdir(RECORDING_DIR) if f.endswith(".csv")]

        raw_files.sort(key=lambda fn: os.path.getmtime(os.path.join(RECORDING_DIR, fn)))
        csv_files.sort(key=lambda fn: os.path.getmtime(os.path.join(RECORDING_DIR, fn)))

        latest_raw = raw_files[-1] if raw_files else None
        latest_csv = csv_files[-1] if csv_files else None

        return latest_raw, latest_csv
    except FileNotFoundError:
        return None, None

# ---------- Recordings ----------
@app.get("/recordings")
def get_recordings(patient_id: str = Query(...), patient_name: str = Query(None)):
    """Return recordings filtered by patient name/id."""
    if not os.path.exists(RECORDING_DIR):
        raise HTTPException(status_code=404, detail="Recording directory not found")

    prefix = (patient_name or patient_id).lower().replace(" ", "_")
    recordings = []

    for fname in os.listdir(RECORDING_DIR):
        if fname.lower().startswith(prefix) and fname.endswith("_angles.csv"):
            label = fname.replace("_angles.csv", "").replace("_", " ").title()
            recordings.append({
                "id": fname.replace(".csv", ""),
                "label": label,
                "file": fname
            })

    if not recordings:
        raise HTTPException(status_code=404, detail=f"No recordings found for {prefix}")

    return recordings

@app.get("/recordings/{rid}")
def get_recording(rid: str):
    """Return angle-time data for given recording."""
    csv_path = os.path.join(RECORDING_DIR, f"{rid}.csv")
    if not os.path.exists(csv_path):
        raise HTTPException(status_code=404, detail=f"No CSV file found for recording {rid}")

    data = []
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                data.append({
                    "time": float(row["time_s"]),
                    "angle": float(row["angle_deg"]) if row["angle_deg"] else None,
                })
            except Exception:
                continue

    return JSONResponse({
        "id": rid,
        "label": os.path.basename(csv_path).replace("_", " ").replace(".csv", "").title(),
        "file": os.path.basename(csv_path),
        "data": data
    })

# ---------- Patients ----------
@app.get("/patients")
def get_patients():
    """List all patients."""
    return load_json(PATIENT_FILE)

@app.get("/patients/{pid}")
def get_patient(pid: str):
    """Get one patient + their recordings."""
    patients = load_json(PATIENT_FILE)
    patient = next((p for p in patients if p.get("id") == pid), None)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    patient["recordings"] = [r for r in load_json(RECORDING_FILE) if r.get("patient_id") == pid]
    return patient

@app.post("/patients")
def create_patient(payload: dict):
    """Add new patient."""
    patients = load_json(PATIENT_FILE)
    new_patient = {"id": str(uuid.uuid4()), **payload}
    patients.append(new_patient)
    save_json(PATIENT_FILE, patients)
    return new_patient

@app.put("/patients/{pid}")
def update_patient(pid: str, payload: dict):
    """Update patient details."""
    patients = load_json(PATIENT_FILE)
    for p in patients:
        if p.get("id") == pid:
            p.update(payload)
            save_json(PATIENT_FILE, patients)
            return p
    raise HTTPException(status_code=404, detail="Patient not found")

@app.delete("/patients/{pid}")
def delete_patient(pid: str):
    """Delete a patient."""
    patients = [p for p in load_json(PATIENT_FILE) if p.get("id") != pid]
    save_json(PATIENT_FILE, patients)
    return {"ok": True}

# ---------- Analyze (Streaming) ----------
@app.post("/analyze")
async def analyze_patient(request: Request):
    """Run main.py and stream output live, then save CSV & metadata."""
    data = await request.json()
    patient_id = data.get("patient_id")
    patient_name = data.get("name", "unknown")

    if not patient_id:
        raise HTTPException(status_code=400, detail="Missing patient_id")

    print(f"=== Starting analysis for patient {patient_id} ({patient_name}) ===")

    async def stream_mainpy():
        env = os.environ.copy()
        env.setdefault("AUTO_START", "1")

        process = await asyncio.create_subprocess_exec(
            "python", "src/main.py",
            cwd=ROOT_DIR,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        async for line in process.stdout:
            yield line.decode("utf-8")

        await process.wait()

        # ---------- POST-PROCESS ----------
        latest_raw, latest_csv = find_latest_raw_and_csv()
        if not latest_csv:
            yield "\n⚠️ No CSV file found after analysis.\n"
            return

        os.makedirs(RECORDING_DIR, exist_ok=True)

        slug = slugify(patient_name)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        new_filename = f"{slug}_{timestamp}_{abs(hash(timestamp)) % 10**9}_angles.csv"

        src_csv = os.path.join(RECORDING_DIR, latest_csv)
        dest_csv = os.path.join(RECORDING_DIR, new_filename)
        shutil.copy(src_csv, dest_csv)

        yield f"\n📁 Saved new recording for {patient_name}: {new_filename}\n"

        # ---------- Save metadata ----------
        recordings_path = os.path.join(DATA_DIR, "recordings.json")
        recordings = load_json(recordings_path)
        rec_entry = {
            "patient_id": patient_id,
            "name": patient_name,
            "timestamp": timestamp,
            "csv": new_filename,
            "raw": latest_raw,
        }
        recordings.append(rec_entry)
        save_json(recordings_path, recordings)

        yield "\n✅ Metadata updated and recording saved.\n"
        yield "🎉 Analysis complete!\n"

    return StreamingResponse(stream_mainpy(), media_type="text/plain")
