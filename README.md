# Technemachina Daemon v0.1

A local-first Python3 engineering companion powered by FastAPI, Ollama, and SQLite.

## v0.1 Features

- Local chat endpoint
- Code explanation endpoint
- Debugging endpoint
- SQLite conversation history
- Strict localhost host validation
- Clean modular backend

## Requirements

- Python 3.10+
- Ollama installed and running
- A local model pulled, for example:

```bash
ollama pull qwen2.5-coder:7b
```

## Setup

```bash
cd Technemachina-Daemon-v0.1/daemon
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Then open:

```text
frontend/index.html
```

in your browser.

## Roadmap

v0.2:
- risk.py classifier
- pip-audit dependency scan
- dedupe.py duplicate scanner
- sandbox execution boundary
- task manager / kill switch foundation
