#!/usr/bin/env python3
from pathlib import Path
from datetime import datetime
import json
import re
import sys
import urllib.request
import urllib.error

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
LOG_DIR = ROOT / "logs" / "diagnostics"
LOG_DIR.mkdir(parents=True, exist_ok=True)

BACKEND_MAP_URL = "http://127.0.0.1:8000/synapse/map"
BACKEND_ANALYSIS_URL = "http://127.0.0.1:8000/synapse/analysis"
FRONTEND_INDEX_URL = "http://127.0.0.1:5173/index.html"
FRONTEND_MAIN_URL = "http://127.0.0.1:5173/main.js"

report = []
failed = False

def line(text=""):
    report.append(text)
    print(text)

def fail(text):
    global failed
    failed = True
    line(f"❌ {text}")

def ok(text):
    line(f"✅ {text}")

def warn(text):
    line(f"⚠️  {text}")

def fetch_json(url):
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))

def fetch_text(url):
    with urllib.request.urlopen(url, timeout=10) as r:
        return r.read().decode("utf-8", errors="ignore")

line("SYNAPSE MAP SYSTEM DIAGNOSTIC")
line(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
line(f"Project: {ROOT}")
line("")

# 1. Required local files
required_files = [
    FRONTEND / "index.html",
    FRONTEND / "main.js",
    FRONTEND / "style.css",
    FRONTEND / "synapse" / "SynapseDataAdapter.js",
    FRONTEND / "synapse" / "SynapseRendererCanvas.js",
    FRONTEND / "synapse" / "SynapseRendererRegistry.js",
]

for path in required_files:
    if path.exists():
        ok(f"Found {path.relative_to(ROOT)}")
    else:
        fail(f"Missing {path.relative_to(ROOT)}")

line("")

# 2. Backend map endpoint
try:
    data = fetch_json(BACKEND_MAP_URL)
    nodes = data.get("nodes", [])
    edges = data.get("edges", [])
    if len(nodes) > 0 and len(edges) > 0:
        ok(f"Backend /synapse/map online: {len(nodes)} nodes / {len(edges)} edges")
    else:
        fail(f"Backend /synapse/map returned empty map: {len(nodes)} nodes / {len(edges)} edges")
except Exception as exc:
    fail(f"Backend /synapse/map failed: {exc}")

# 3. Backend analysis endpoint
try:
    analysis = fetch_json(BACKEND_ANALYSIS_URL)
    totals = analysis.get("totals", {})
    ok(f"Backend /synapse/analysis online: {totals.get('nodes', 'unknown')} analysis nodes / {totals.get('edges', 'unknown')} analysis edges")
except Exception as exc:
    warn(f"Backend /synapse/analysis failed or unavailable: {exc}")

line("")

# 4. Frontend server
try:
    index_text = fetch_text(FRONTEND_INDEX_URL)
    if "synapse-canvas" in index_text and "main.js" in index_text:
        ok("Frontend index served and contains Synapse canvas + main.js")
    else:
        fail("Frontend index served, but Synapse canvas or main.js marker is missing")
except Exception as exc:
    fail(f"Frontend index failed: {exc}")

try:
    main_served = fetch_text(FRONTEND_MAIN_URL)
    if "synapse-canvas" in main_served or "synapse/map" in main_served:
        ok("Frontend main.js served")
    else:
        warn("Frontend main.js served but expected Synapse markers were weak")
except Exception as exc:
    fail(f"Frontend main.js failed: {exc}")

line("")

# 5. Static source scan for dangerous relative backend endpoint
main_path = FRONTEND / "main.js"
if main_path.exists():
    main_text = main_path.read_text(encoding="utf-8", errors="ignore")

    good_url_count = main_text.count("http://127.0.0.1:8000/synapse/map")

    dangerous_patterns = [
        r'fetch\(\s*["\']\/synapse\/map["\']',
        r'fetch\(\s*`\/synapse\/map`',
        r'=\s*["\']\/synapse\/map["\']',
        r'=\s*`\/synapse\/map`',
    ]

    dangerous_hits = []
    for pattern in dangerous_patterns:
        dangerous_hits.extend(re.findall(pattern, main_text))

    if good_url_count >= 1:
        ok(f"main.js points Synapse data to backend port 8000 ({good_url_count} reference)")
    else:
        fail("main.js does not contain backend Synapse URL http://127.0.0.1:8000/synapse/map")

    if dangerous_hits:
        fail(f"main.js still contains dangerous relative /synapse/map reference(s): {dangerous_hits}")
    else:
        ok("No dangerous relative /synapse/map fetch detected in main.js")

    analysis_good_url_count = main_text.count("http://127.0.0.1:8000/synapse/analysis")
    dangerous_analysis_patterns = [
        r'fetch\(\s*["\']\/synapse\/analysis["\']',
        r'fetch\(\s*`\/synapse\/analysis`',
        r'=\s*["\']\/synapse\/analysis["\']',
        r'=\s*`\/synapse\/analysis`',
    ]

    dangerous_analysis_hits = []
    for pattern in dangerous_analysis_patterns:
        dangerous_analysis_hits.extend(re.findall(pattern, main_text))

    if analysis_good_url_count >= 1:
        ok(f"main.js points Synapse analysis to backend port 8000 ({analysis_good_url_count} reference)")
    else:
        fail("main.js does not contain backend Synapse analysis URL http://127.0.0.1:8000/synapse/analysis")

    if dangerous_analysis_hits:
        fail(f"main.js still contains dangerous relative /synapse/analysis reference(s): {dangerous_analysis_hits}")
    else:
        ok("No dangerous relative /synapse/analysis fetch detected in main.js")

line("")

# 6. Index cache-bust check
index_path = FRONTEND / "index.html"
if index_path.exists():
    html = index_path.read_text(encoding="utf-8", errors="ignore")
    if "main.js?v=" in html:
        ok("index.html cache-busts main.js")
    else:
        warn("index.html loads main.js without cache-bust. Safari may reuse stale JS.")

line("")

# 7. Final status
if failed:
    line("RESULT: FAIL — Synapse Map guard found a blocking issue.")
    code = 1
else:
    line("RESULT: PASS — Synapse Map data path and renderer files look healthy.")
    code = 0

log_path = LOG_DIR / f"synapse_doctor_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
log_path.write_text("\n".join(report) + "\n", encoding="utf-8")
line(f"Saved diagnostic log: {log_path.relative_to(ROOT)}")

sys.exit(code)
