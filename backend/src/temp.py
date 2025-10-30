import os
DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data'))
PATIENT_FILE = os.path.join(DATA_DIR, 'patients.json')

print(PATIENT_FILE)