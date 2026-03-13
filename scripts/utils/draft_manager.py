"""Draft lifecycle management — read, move, and update draft JSON files."""

import json
import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


def _get_root() -> Path:
    root = os.environ.get("AUTO_POSTER_ROOT")
    if root:
        return Path(root)
    return Path(__file__).resolve().parent.parent.parent


def _ensure_dirs(root: Path) -> None:
    for sub in ("drafts/pending", "drafts/posted", "drafts/failed"):
        (root / sub).mkdir(parents=True, exist_ok=True)


def get_next_draft() -> dict | None:
    """Return the oldest pending draft (by mtime) or None."""
    root = _get_root()
    _ensure_dirs(root)
    pending = root / "drafts" / "pending"
    drafts = sorted(pending.glob("draft-*.json"), key=lambda p: p.stat().st_mtime)
    if not drafts:
        logger.info("No pending drafts found")
        return None

    path = drafts[0]
    logger.info("Picked up draft: %s", path.name)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    data["_path"] = str(path)
    return data


def mark_posted(draft: dict, platforms_posted: list[str]) -> None:
    """Add posting metadata and move draft to posted/."""
    root = _get_root()
    _ensure_dirs(root)
    src = Path(draft["_path"])
    draft.pop("_path", None)
    draft["status"] = "posted"
    draft["posted_at"] = datetime.now(timezone.utc).isoformat()
    draft["platforms_posted"] = platforms_posted

    dest = root / "drafts" / "posted" / src.name
    with open(src, "w", encoding="utf-8") as f:
        json.dump(draft, f, indent=2)
    shutil.move(str(src), str(dest))
    logger.info("Draft %s moved to posted/ (platforms: %s)", src.name, platforms_posted)


def mark_failed(draft: dict, error: str) -> None:
    """Add failure metadata and move draft to failed/."""
    root = _get_root()
    _ensure_dirs(root)
    src = Path(draft["_path"])
    draft.pop("_path", None)
    draft["status"] = "failed"
    draft["failed_at"] = datetime.now(timezone.utc).isoformat()
    draft["error"] = error

    dest = root / "drafts" / "failed" / src.name
    with open(src, "w", encoding="utf-8") as f:
        json.dump(draft, f, indent=2)
    shutil.move(str(src), str(dest))
    logger.info("Draft %s moved to failed/ (error: %s)", src.name, error)
