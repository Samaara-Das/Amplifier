"""Nuitka build script for macOS — produces dist/mac/Amplifier.app bundle.

CRITICAL — Patchright + Chromium bundling note:
    Patchright bundles its Chromium browser at runtime via `patchright install chromium`.
    Nuitka cannot bundle the ~150 MB browser binary itself (it lives outside the Python
    package tree). The macOS installer (pkgbuild/productbuild) is responsible for running
    `patchright install chromium` via the postinstall script (option b, chosen for v1) so
    the Chromium download stays independent of app updates and the installer stays smaller.
    The app checks for the browser on first launch and prompts a one-time download if missing.
    See scripts/build/installer/postinstall.sh and scripts/utils/auto_update.py.
"""

import json
import subprocess
import sys
from pathlib import Path

# Repo root is two levels up from this file (scripts/build/build_mac.py)
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

    # macOS-specific flags
    mac = spec.get("mac", {})
    args += ["--macos-create-app-bundle"]

    app_name = spec.get("name", "Amplifier")
    args.append(f"--macos-app-name={app_name}")

    icon = mac.get("icon")
    if icon:
        args.append(f"--macos-app-icon={icon}")

    bundle_id = mac.get("bundle_identifier")
    if bundle_id:
        args.append(f"--macos-app-bundle-id={bundle_id}")

    args += [
        "--output-dir=dist/mac",
        f"--output-filename={app_name}",
    ]

    # Entry point
    args.append(spec["entry_point"])

    return args


def main() -> int:
    spec = load_spec()
    args = build_args(spec)

    print(f"[build_mac] Building {spec['name']} v{spec['version']} for macOS")
    print(f"[build_mac] Command: {' '.join(args)}")
    print("[build_mac] Starting Nuitka compilation (this can take several minutes) ...")

    # Run from repo root so relative paths in spec are resolved correctly
    result = subprocess.run(args, cwd=str(REPO_ROOT))

    if result.returncode != 0:
        print(f"[build_mac] ERROR: Nuitka exited with code {result.returncode}")
        return result.returncode

    app_path = REPO_ROOT / "dist" / "mac" / f"{spec['name']}.app"
    if app_path.exists():
        print(f"[build_mac] SUCCESS: {app_path}")
    else:
        print("[build_mac] WARNING: Nuitka reported success but .app bundle not found.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
