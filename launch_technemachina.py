#!/usr/bin/env python3
import os
import sys
import time
import signal
import subprocess
import webbrowser
from pathlib import Path

ROOT = Path.home() / "Downloads" / "Technemachina-Daemon-v0.1"
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

time.sleep(3)

frontend = start(
    "frontend on 5173",
    [PYTHON, "-m", "http.server", "5173"],
    FRONTEND
)

time.sleep(2)

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
