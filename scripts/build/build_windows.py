"""Nuitka build script for Windows — produces dist/windows/Amplifier.exe.

CRITICAL — Patchright + Chromium bundling note:
    Patchright bundles its Chromium browser at runtime via `patchright install chromium`.
    Nuitka cannot bundle the ~150 MB browser binary itself (it lives outside the Python
    package tree). The Inno Setup installer is responsible for running
    `patchright install chromium` as a post-install step (option b, chosen for v1) so
    the Chromium download stays independent of app updates and the installer stays smaller.
    The app checks for the browser on first launch and prompts a one-time download if missing.
    See scripts/build/installer/windows.iss [Run] section and scripts/utils/auto_update.py.
"""

import json
import subprocess
import sys
from pathlib import Path

# Repo root is two levels up from this file (scripts/build/build_windows.py)
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SPEC_PATH = REPO_ROOT / "scripts" / "build" / "spec.json"


def load_spec() -> dict:
    with open(SPEC_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def build_args(spec: dict) -> list[str]:
    """Construct the Nuitka command-line argument list from spec.json."""
    args = [sys.executable, "-m", "nuitka"]

    args += ["--onefile", "--standalone"]
    args += ["--enable-plugin=anti-bloat"]

    # Include packages declared in spec
    for pkg in spec.get("include_packages", []):
        args.append(f"--include-package={pkg}")

    # Include data dirs declared in spec
    for entry in spec.get("include_data_dirs", []):
        src = entry["src"]
        dest = entry["dest"]
        args.append(f"--include-data-dir={src}={dest}")

    # Windows-specific flags
    win = spec.get("windows", {})
    if not win.get("console", True):
        args += ["--windows-console-mode=disable"]

    icon = win.get("icon")
    if icon:
        args.append(f"--windows-icon-from-ico={icon}")

    args += [
        "--output-dir=dist/windows",
        f"--output-filename={spec['name']}.exe",
    ]

    # Entry point
    args.append(spec["entry_point"])

    return args


def main() -> int:
    spec = load_spec()
    args = build_args(spec)

    print(f"[build_windows] Building {spec['name']} v{spec['version']} for Windows")
    print(f"[build_windows] Command: {' '.join(args)}")
    print("[build_windows] Starting Nuitka compilation (this can take several minutes) ...")

    # Run from repo root so relative paths in spec are resolved correctly
    result = subprocess.run(args, cwd=str(REPO_ROOT))

    if result.returncode != 0:
        print(f"[build_windows] ERROR: Nuitka exited with code {result.returncode}")
        return result.returncode

    exe_path = REPO_ROOT / "dist" / "windows" / f"{spec['name']}.exe"
    if exe_path.exists():
        size_mb = exe_path.stat().st_size / (1024 * 1024)
        print(f"[build_windows] SUCCESS: {exe_path} ({size_mb:.1f} MB)")
    else:
        print("[build_windows] WARNING: Nuitka reported success but output binary not found.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
