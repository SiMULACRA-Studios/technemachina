Companion Visual Archive
========================

This directory stores deterministic local captures of the isolated
Companion Hologram prototype. It is intentionally separate from the
production frontend and does not change the Companion visual
implementation.

Capture Types
-------------

- `baseline`: the preserved current visual state before a future visual patch.
- `before`: a pre-change capture for comparison work.
- `after`: a post-change capture for comparison work.
- `manual`: an explicit ad hoc capture.

Command
-------

Create the dedicated local tooling environment from
`tools/companion_archive/requirements.txt`, then run from the repository
root:

```bash
tools/companion_archive/.venv/bin/python tools/companion_archive/capture_companion.py baseline
```

Other accepted classifications:

```bash
tools/companion_archive/.venv/bin/python tools/companion_archive/capture_companion.py before
tools/companion_archive/.venv/bin/python tools/companion_archive/capture_companion.py after
tools/companion_archive/.venv/bin/python tools/companion_archive/capture_companion.py manual
```

Output Layout
-------------

```text
docs/companion-progress/
├── README.md
├── latest.png
├── manifest.json
├── manifest.example.json
├── raw/
├── captures/
├── diagnostics/
└── archive/
```

Baseline captures are written under `raw/`. Non-baseline captures are
written under `captures/`. Failed verification images are written under
`diagnostics/`. Generated captures remain local by default and are ignored
by Git.

`manifest.json` is local runtime evidence and is ignored.
`manifest.example.json` documents the committed starter structure for a
fresh checkout.

The script updates `latest.png` to the latest canonical-eye capture using
an atomic replacement. Timestamped capture files are never overwritten.

Determinism
-----------

The capture script uses:

- viewport `1440 x 900`
- device-pixel ratio `1`
- installed Google Chrome through Python Playwright
- reduced motion
- locale `en-US`
- the isolated route:
  `http://127.0.0.1:5173/companion-hologram-test.html`

The script reuses an already-running valid server on `127.0.0.1:5173`.
If no valid server is present, it starts:

```bash
cd frontend
python3 -m http.server 5173 --bind 127.0.0.1
```

Only a server started by the capture script is terminated by the capture
script.

Verification
------------

The script does not rely solely on WebGL `readPixels()`. It captures a
screenshot of the canonical region and analyzes pixels with Pillow. A
capture is accepted only when the screenshot has meaningful nonblack
pixels and luminance variation above conservative thresholds.
