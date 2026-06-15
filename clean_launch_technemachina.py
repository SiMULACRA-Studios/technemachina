#!/usr/bin/env python3
import signal
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from env_loader import load_project_env
import urllib.request
import json

ROOT = Path.home() / "Downloads" / "Technemachina-Daemon-v0.1"
load_project_env(ROOT)
DAEMON = ROOT / "daemon"
FRONTEND = ROOT / "frontend"

BACKEND_PYTHON = DAEMON / ".venv" / "bin" / "python"
if not BACKEND_PYTHON.exists():
    BACKEND_PYTHON = Path(sys.executable)

processes = []

def kill_port(port):
    print(f"Clearing port {port}...")
    result = subprocess.run(
        ["bash", "-lc", f"lsof -ti tcp:{port}"],
        capture_output=True,
        text=True
    )
    pids = [pid.strip() for pid in result.stdout.splitlines() if pid.strip()]
    if not pids:
        print(f"  port {port} already clear")
    for pid in pids:
        print(f"  killing PID {pid} on port {port}")
        subprocess.run(["kill", "-9", pid], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def start(name, cmd, cwd):
    print(f"\nStarting {name}...")
    p = subprocess.Popen(cmd, cwd=str(cwd))
    processes.append((name, p))
    return p

def fetch_text(url):
    with urllib.request.urlopen(url, timeout=10) as r:
        return r.read(500).decode("utf-8", errors="ignore")

def fetch_json(url):
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))

def wait_for(url, label, seconds=25):
    print(f"Waiting for {label}...")
    deadline = time.time() + seconds
    last_error = None

    while time.time() < deadline:
        try:
            fetch_text(url)
            print(f"  {label} online")
            return True
        except Exception as e:
            last_error = e
            time.sleep(1)

    print(f"  {label} failed: {last_error}")
    return False

def stop_all(*_):
    print("\nStopping Technemachina...")
    for name, p in processes:
        if p.poll() is None:
            print(f"Stopping {name}")
            p.terminate()

    time.sleep(1)

    for name, p in processes:
        if p.poll() is None:
            p.kill()

    print("Stopped.")
    sys.exit(0)

signal.signal(signal.SIGINT, stop_all)
signal.signal(signal.SIGTERM, stop_all)

print("TECHNEMACHINA CLEAN LAUNCH")
print(f"Project: {ROOT}")

kill_port(8000)
kill_port(5173)

start(
    "backend on 8000",
    [str(BACKEND_PYTHON), "-m", "uvicorn", "app:app", "--reload"],
    DAEMON
)

time.sleep(4)

start(
    "frontend on 5173",
    [sys.executable, "-m", "http.server", "5173"],
    FRONTEND
)

time.sleep(2)

wait_for("http://127.0.0.1:8000/synapse/map", "backend /synapse/map")
wait_for("http://127.0.0.1:5173/index.html", "frontend index")

print("\nRunning Synapse doctor...")
doctor = ROOT / "scripts" / "synapse_doctor.py"
if doctor.exists():
    subprocess.run([sys.executable, str(doctor)], cwd=str(ROOT))
else:
    print("No scripts/synapse_doctor.py found.")

print("\nDirect route checks:")
try:
    data = fetch_json("http://127.0.0.1:8000/synapse/map")
    print("  map nodes:", len(data.get("nodes", [])))
    print("  map edges:", len(data.get("edges", [])))
except Exception as e:
    print("  map failed:", e)

try:
    analysis = fetch_json("http://127.0.0.1:8000/synapse/analysis")
    totals = analysis.get("totals", {})
    print("  analysis nodes:", totals.get("nodes"))
    print("  analysis edges:", totals.get("edges"))
except Exception as e:
    print("  analysis failed:", e)

url = "http://127.0.0.1:5173/index.html?v=clean-launch-0412"
print(f"\nOpening browser: {url}")
webbrowser.open(url)

print("\nTechnemachina clean launch is running.")
print("Keep this Terminal open.")
print("Press Control+C here later to stop backend and frontend.")
print("In the browser, press Command+Shift+R, then click Synapse Map.\n")

while True:
    time.sleep(1)
