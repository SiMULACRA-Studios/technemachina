#!/bin/bash
set -euo pipefail

ROOT="$HOME/Downloads/Technemachina-Daemon-v0.1"
CHECKPOINT="$ROOT/recovery_snapshots/20260614_141551_CONSTELLATION_VISUALLY_CONFIRMED"
SAFETY="$ROOT/recovery_snapshots/$(date +%Y%m%d_%H%M%S)_BEFORE_EXPLICIT_RESTORE"

if [ ! -d "$CHECKPOINT" ]; then
  echo "Checkpoint not found:"
  echo "$CHECKPOINT"
  exit 1
fi

cd "$ROOT"

echo "This will restore the exact checkpoint:"
echo "$CHECKPOINT"
echo
read -r -p "Type RESTORE to continue: " CONFIRM

if [ "$CONFIRM" != "RESTORE" ]; then
  echo "Cancelled."
  exit 1
fi

mkdir -p "$SAFETY/frontend" "$SAFETY/backend"

[ -f frontend/index.html ] && cp frontend/index.html "$SAFETY/frontend/index.html"
[ -f frontend/main.js ] && cp frontend/main.js "$SAFETY/frontend/main.js"
[ -f frontend/style.css ] && cp frontend/style.css "$SAFETY/frontend/style.css"
[ -f daemon/app.py ] && cp daemon/app.py "$SAFETY/backend/app.py"

cp "$CHECKPOINT/frontend/index.html" frontend/index.html
cp "$CHECKPOINT/frontend/main.js" frontend/main.js
cp "$CHECKPOINT/frontend/style.css" frontend/style.css

if [ -d "$CHECKPOINT/frontend/synapse" ]; then
  mkdir -p frontend/synapse
  cp -R "$CHECKPOINT/frontend/synapse/." frontend/synapse/
fi

if [ -f "$CHECKPOINT/backend/app.py" ]; then
  cp "$CHECKPOINT/backend/app.py" daemon/app.py
fi

echo
echo "Restore complete."
echo "Pre-restore safety copy:"
echo "$SAFETY"
echo
echo "Restart Technemachina, then run:"
echo "python3 scripts/synapse_doctor.py"
