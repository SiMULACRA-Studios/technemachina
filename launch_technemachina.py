#!/usr/bin/env python3
import os
import sys
import time
import signal
import subprocess
import webbrowser
import urllib.request
from pathlib import Path
from env_loader import load_project_env

ROOT = Path(__file__).resolve().parent
load_project_env(ROOT)
DAEMON = ROOT / "daemon"
FRONTEND = ROOT / "frontend"
PYTHON = sys.executable

backend_python = DAEMON / ".venv" / "bin" / "python"
if not backend_python.exists():
    backend_python = Path(PYTHON)

processes = []

def start(name, cmd, cwd):
    print(f"\nStarting {name}...")
    p = subprocess.Popen(cmd, cwd=str(cwd))
    processes.append((name, p))
    return p


def wait_for(url, label, seconds=25):
    """Wait until a local HTTP service responds or the timeout expires."""
    print(f"Waiting for {label}...")
    deadline = time.time() + seconds
    last_error = None

    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                response.read(1)
            print(f"  {label} online")
            return True
        except Exception as exc:
            last_error = exc
            time.sleep(1)

    print(f"  {label} failed: {last_error}")
    return False

def stop_all(*_):
    print("\nStopping Technemachina servers...")
    for name, p in processes:
        if p.poll() is None:
            print(f"Stopping {name}...")
            p.terminate()
    time.sleep(1)
    for name, p in processes:
        if p.poll() is None:
            p.kill()
    print("Stopped.")
    sys.exit(0)

signal.signal(signal.SIGINT, stop_all)
signal.signal(signal.SIGTERM, stop_all)

backend = start(
    "backend on 8000",
    [str(backend_python), "-m", "uvicorn", "app:app", "--reload"],
    DAEMON
)

frontend = start(
    "frontend on 5173",
    [PYTHON, "-m", "http.server", "5173"],
    FRONTEND
)

backend_ready = wait_for(
    "http://127.0.0.1:8000/synapse/map",
    "backend /synapse/map",
)

frontend_ready = wait_for(
    "http://127.0.0.1:5173/index.html",
    "frontend index",
)

if not backend_ready or not frontend_ready:
    print("\nStartup verification failed. Synapse doctor will still run for diagnostics.")

print("\nRunning Synapse doctor...")
doctor = ROOT / "scripts" / "synapse_doctor.py"
if doctor.exists():
    subprocess.run([PYTHON, str(doctor)], cwd=str(ROOT))
else:
    print("No scripts/synapse_doctor.py found yet.")

url = "http://127.0.0.1:5173/index.html?v=python-launch"
print(f"\nOpening browser: {url}")
webbrowser.open(url)

print("\nTechnemachina is running.")
print("Press Control+C in this Terminal to stop backend and frontend.")
print("Then click Synapse Map in the browser.\n")

while True:
    time.sleep(1)
