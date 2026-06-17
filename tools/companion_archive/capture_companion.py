#!/usr/bin/env python3
"""Deterministic Companion Hologram visual capture tool."""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from PIL import Image
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright


SCRIPT_VERSION = "0.1.0"
ROUTE = "http://127.0.0.1:5173/companion-hologram-test.html"
SERVER_HOST = "127.0.0.1"
SERVER_PORT = "5173"
VIEWPORT = {"width": 1440, "height": 900}
DEVICE_SCALE_FACTOR = 1
LOCALE = "en-US"
VALID_CLASSIFICATIONS = {"baseline", "before", "after", "manual"}
CANVAS_SELECTOR = ".companion-hologram-canvas"
STAGE_SELECTOR = ".hologram-stage"

THRESHOLDS = {
    "nearBlackLuminance": 8,
    "meaningfulLuminance": 18,
    "minimumNonblackRatio": 0.002,
    "minimumMeaningfulRatio": 0.0008,
    "minimumLuminanceVariance": 4.0,
    "minimumMeaningfulWidth": 12,
    "minimumMeaningfulHeight": 12,
}

RELEVANT_SOURCE_FILES = [
    "frontend/companion/CompanionHologram.js",
    "frontend/companion/companion-hologram-test.css",
    "frontend/companion-hologram-test.html",
]


@dataclass
class ServerState:
    reused_existing: bool
    started_by_script: bool
    process: subprocess.Popen[str] | None = None


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def utc_timestamp() -> datetime:
    return datetime.now(timezone.utc)


def timestamp_slug(moment: datetime) -> str:
    return moment.strftime("%Y%m%dT%H%M%S.%fZ")


def rel(path: Path) -> str:
    return path.relative_to(repo_root()).as_posix()


def run_git(args: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repo_root(),
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError:
        return ""
    return result.stdout.strip()


def git_metadata() -> dict[str, Any]:
    status = run_git(["status", "--porcelain", "--untracked-files=all"])
    changed_files = []
    for line in status.splitlines():
        if not line:
            continue
        path = line[3:] if len(line) > 3 else line
        if path in RELEVANT_SOURCE_FILES:
            changed_files.append({"status": line[:2], "path": path})

    return {
        "commit": run_git(["rev-parse", "HEAD"]),
        "branch": run_git(["branch", "--show-current"]),
        "dirty": bool(status),
        "status": "dirty" if status else "clean",
        "relevantChangedFiles": changed_files,
    }


def ensure_archive_dirs() -> dict[str, Path]:
    base = repo_root() / "docs" / "companion-progress"
    dirs = {
        "base": base,
        "raw": base / "raw",
        "captures": base / "captures",
        "diagnostics": base / "diagnostics",
        "archive": base / "archive",
    }
    for directory in dirs.values():
        directory.mkdir(parents=True, exist_ok=True)
    return dirs


def ensure_manifest(manifest_path: Path) -> None:
    if manifest_path.exists():
        return
    write_json_atomic(manifest_path, {"schemaVersion": 1, "captures": []})


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    tmp.write_text(
        json.dumps(payload, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)


def append_manifest_record(record: dict[str, Any]) -> None:
    manifest_path = repo_root() / "docs" / "companion-progress" / "manifest.json"
    ensure_manifest(manifest_path)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Manifest is not valid JSON: {manifest_path}") from exc

    captures = manifest.setdefault("captures", [])
    if not isinstance(captures, list):
        raise RuntimeError("Manifest field 'captures' must be a list.")
    captures.append(record)
    write_json_atomic(manifest_path, manifest)


def route_is_valid() -> bool:
    try:
        with urlopen(ROUTE, timeout=2) as response:
            body = response.read(4096).decode("utf-8", errors="replace")
    except (OSError, URLError):
        return False
    return response.status == 200 and "CompanionHologram" in body


def wait_for_route(seconds: float = 8.0) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if route_is_valid():
            return True
        time.sleep(0.25)
    return False


def start_or_reuse_server() -> ServerState:
    if route_is_valid():
        return ServerState(reused_existing=True, started_by_script=False)

    frontend_dir = repo_root() / "frontend"
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "http.server",
            SERVER_PORT,
            "--bind",
            SERVER_HOST,
        ],
        cwd=frontend_dir,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )

    if not wait_for_route():
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
        raise RuntimeError(f"Could not serve expected hologram route: {ROUTE}")

    return ServerState(
        reused_existing=False,
        started_by_script=True,
        process=process,
    )


def stop_started_server(server: ServerState) -> None:
    if not server.started_by_script or server.process is None:
        return
    if server.process.poll() is not None:
        return
    server.process.terminate()
    try:
        server.process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        server.process.kill()


def unique_path(directory: Path, stem: str, suffix: str = ".png") -> Path:
    candidate = directory / f"{stem}{suffix}"
    if not candidate.exists():
        return candidate
    for index in range(1, 1000):
        candidate = directory / f"{stem}_{index}{suffix}"
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Could not allocate unique filename for {stem}{suffix}")


def wait_for_canvas(page: Any) -> dict[str, Any]:
    page.wait_for_load_state("domcontentloaded")
    page.evaluate("() => document.fonts ? document.fonts.ready : Promise.resolve()")
    page.wait_for_selector(CANVAS_SELECTOR, state="attached", timeout=10000)
    page.wait_for_function(
        """selector => {
          const canvas = document.querySelector(selector);
          return Boolean(canvas && canvas.width > 0 && canvas.height > 0);
        }""",
        arg=CANVAS_SELECTOR,
        timeout=10000,
    )
    page.evaluate(
        """() => new Promise(resolve => {
          requestAnimationFrame(() => requestAnimationFrame(resolve));
        })"""
    )
    page.wait_for_timeout(350)
    return page.evaluate(
        """selector => {
          const canvas = document.querySelector(selector);
          const rect = canvas.getBoundingClientRect();
          return {
            width: canvas.width,
            height: canvas.height,
            clientWidth: rect.width,
            clientHeight: rect.height,
          };
        }""",
        arg=CANVAS_SELECTOR,
    )


def crop_canonical(canvas_path: Path, canonical_path: Path) -> None:
    with Image.open(canvas_path) as image:
        image = image.convert("RGBA")
        width, height = image.size
        left = int(width * 0.08)
        top = int(height * 0.00)
        right = int(width * 0.92)
        bottom = int(height * 1.00)
        image.crop((left, top, right, bottom)).save(canonical_path)


def analyze_image(path: Path) -> dict[str, Any]:
    with Image.open(path) as image:
        rgba = image.convert("RGBA")
        pixels = list(rgba.getdata())
        width, height = rgba.size

    total = width * height
    if total == 0:
        return {
            "passed": False,
            "reason": "zero-sized image",
            "width": width,
            "height": height,
            "totalPixels": total,
            "thresholds": THRESHOLDS,
        }

    luminances: list[float] = []
    nonblack = 0
    near_black = 0
    meaningful = 0
    min_x = width
    min_y = height
    max_x = -1
    max_y = -1

    for index, (red, green, blue, alpha) in enumerate(pixels):
        lum = 0.2126 * red + 0.7152 * green + 0.0722 * blue
        if alpha == 0:
            lum = 0
        luminances.append(lum)

        if lum <= THRESHOLDS["nearBlackLuminance"]:
            near_black += 1
        else:
            nonblack += 1

        if lum > THRESHOLDS["meaningfulLuminance"]:
            meaningful += 1
            x = index % width
            y = index // width
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            max_x = max(max_x, x)
            max_y = max(max_y, y)

    mean = sum(luminances) / total
    variance = sum((value - mean) ** 2 for value in luminances) / total
    bbox = None
    bbox_width = 0
    bbox_height = 0
    if max_x >= min_x and max_y >= min_y:
        bbox = {
            "x": min_x,
            "y": min_y,
            "width": max_x - min_x + 1,
            "height": max_y - min_y + 1,
        }
        bbox_width = bbox["width"]
        bbox_height = bbox["height"]

    near_black_ratio = near_black / total
    nonblack_ratio = nonblack / total
    meaningful_ratio = meaningful / total

    passed = (
        nonblack_ratio >= THRESHOLDS["minimumNonblackRatio"]
        and meaningful_ratio >= THRESHOLDS["minimumMeaningfulRatio"]
        and variance >= THRESHOLDS["minimumLuminanceVariance"]
        and bbox_width >= THRESHOLDS["minimumMeaningfulWidth"]
        and bbox_height >= THRESHOLDS["minimumMeaningfulHeight"]
        and not math.isclose(variance, 0.0)
    )

    return {
        "passed": passed,
        "width": width,
        "height": height,
        "totalPixels": total,
        "nearBlackPixelRatio": near_black_ratio,
        "nonblackPixelRatio": nonblack_ratio,
        "meaningfulPixelRatio": meaningful_ratio,
        "luminanceMean": mean,
        "luminanceVariance": variance,
        "meaningfulBoundingBox": bbox,
        "thresholds": THRESHOLDS,
    }


def atomic_copy(source: Path, destination: Path) -> None:
    tmp = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
    shutil.copy2(source, tmp)
    os.replace(tmp, destination)


def move_to_diagnostics(paths: list[Path], diagnostics_dir: Path, capture_id: str) -> list[str]:
    moved = []
    for path in paths:
        if not path.exists():
            continue
        destination = unique_path(
            diagnostics_dir,
            f"{capture_id}_{path.stem}_failed",
            path.suffix,
        )
        shutil.move(str(path), str(destination))
        moved.append(rel(destination))
    return moved


def browser_capture(classification: str, server: ServerState) -> dict[str, Any]:
    dirs = ensure_archive_dirs()
    moment = utc_timestamp()
    stamp = timestamp_slug(moment)
    capture_id = f"{stamp}_{classification}_{uuid.uuid4().hex[:8]}"
    output_dir = dirs["raw"] if classification == "baseline" else dirs["captures"]

    contextual_path = unique_path(output_dir, f"{capture_id}_contextual")
    canvas_path = unique_path(output_dir, f"{capture_id}_canvas")
    canonical_path = unique_path(output_dir, f"{capture_id}_canonical")

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(
                channel="chrome",
                headless=True,
            )
        except PlaywrightError:
            chrome_path = Path(
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
            )
            if not chrome_path.exists():
                raise RuntimeError(
                    "Installed Google Chrome could not be launched and no "
                    "verified executable path was found. Do not run "
                    "`playwright install` without approval."
                )
            browser = playwright.chromium.launch(
                executable_path=str(chrome_path),
                headless=True,
            )

        context = browser.new_context(
            viewport=VIEWPORT,
            device_scale_factor=DEVICE_SCALE_FACTOR,
            locale=LOCALE,
            reduced_motion="reduce",
        )
        page = context.new_page()
        page.goto(ROUTE, wait_until="domcontentloaded")
        canvas_metrics = wait_for_canvas(page)

        browser_identification = {
            "playwrightBrowserVersion": browser.version,
            "userAgent": page.evaluate("() => navigator.userAgent"),
            "channel": "chrome",
        }

        page.locator(STAGE_SELECTOR).screenshot(path=str(contextual_path))
        page.locator(CANVAS_SELECTOR).screenshot(path=str(canvas_path))
        browser.close()

    crop_canonical(canvas_path, canonical_path)
    canvas_path.unlink(missing_ok=True)

    verification = analyze_image(canonical_path)
    verification["canvas"] = canvas_metrics

    git = git_metadata()
    record = {
        "captureId": capture_id,
        "utcTimestamp": moment.isoformat().replace("+00:00", "Z"),
        "localTimestamp": datetime.now().astimezone().isoformat(),
        "classification": classification,
        "git": git,
        "route": ROUTE,
        "viewport": VIEWPORT,
        "devicePixelRatio": DEVICE_SCALE_FACTOR,
        "browser": browser_identification,
        "contextualImage": rel(contextual_path),
        "canonicalImage": rel(canonical_path),
        "webglVerification": verification,
        "scriptVersion": SCRIPT_VERSION,
        "server": {
            "reusedExisting": server.reused_existing,
            "startedByScript": server.started_by_script,
        },
    }

    if not verification["passed"]:
        diagnostic_images = move_to_diagnostics(
            [contextual_path, canonical_path],
            dirs["diagnostics"],
            capture_id,
        )
        record["diagnosticImages"] = diagnostic_images
        append_manifest_record(record)
        raise RuntimeError(
            "Capture failed nonblank verification. Diagnostic images: "
            + ", ".join(diagnostic_images)
        )

    atomic_copy(canonical_path, dirs["base"] / "latest.png")
    append_manifest_record(record)
    return record


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture deterministic Companion Hologram archive images.",
    )
    parser.add_argument(
        "classification",
        help="Capture classification: baseline, before, after, or manual.",
    )
    args = parser.parse_args()
    if args.classification not in VALID_CLASSIFICATIONS:
        parser.error(
            "unknown classification "
            f"{args.classification!r}; expected one of: "
            + ", ".join(sorted(VALID_CLASSIFICATIONS))
        )
    return args


def main() -> int:
    args = parse_args()
    server = start_or_reuse_server()
    try:
        record = browser_capture(args.classification, server)
    finally:
        stop_started_server(server)

    print(json.dumps({
        "captureId": record["captureId"],
        "classification": record["classification"],
        "contextualImage": record["contextualImage"],
        "canonicalImage": record["canonicalImage"],
        "verificationPassed": record["webglVerification"]["passed"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
