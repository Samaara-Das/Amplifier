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
    for sub in ("drafts/review", "drafts/pending", "drafts/posted", "drafts/failed", "drafts/rejected"):
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


def get_review_drafts() -> list[dict]:
    """Return all drafts in review/ sorted by created_at (oldest first)."""
    root = _get_root()
    _ensure_dirs(root)
    review_dir = root / "drafts" / "review"
    drafts = []
    for path in sorted(review_dir.glob("draft-*.json"), key=lambda p: p.stat().st_mtime):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["_filename"] = path.name
        drafts.append(data)
    return drafts


def approve_draft(filename: str) -> dict:
    """Move a draft from review/ to pending/ and set status to 'pending'."""
    root = _get_root()
    _ensure_dirs(root)
    src = root / "drafts" / "review" / filename
    with open(src, "r", encoding="utf-8") as f:
        data = json.load(f)
    data["status"] = "pending"
    data["approved_at"] = datetime.now(timezone.utc).isoformat()
    with open(src, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    dest = root / "drafts" / "pending" / filename
    shutil.move(str(src), str(dest))
    logger.info("Draft %s approved → pending/", filename)
    return data


def reject_draft(filename: str) -> dict:
    """Move a draft from review/ to rejected/."""
    root = _get_root()
    _ensure_dirs(root)
    src = root / "drafts" / "review" / filename
    with open(src, "r", encoding="utf-8") as f:
        data = json.load(f)
    data["status"] = "rejected"
    data["rejected_at"] = datetime.now(timezone.utc).isoformat()
    with open(src, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    dest = root / "drafts" / "rejected" / filename
    shutil.move(str(src), str(dest))
    logger.info("Draft %s rejected → rejected/", filename)
    return data


def edit_draft(filename: str, updated_content: dict) -> dict:
    """Update the content of a draft in review/ (in-place)."""
    root = _get_root()
    src = root / "drafts" / "review" / filename
    with open(src, "r", encoding="utf-8") as f:
        data = json.load(f)
    for platform, value in updated_content.items():
        if platform in data.get("content", {}):
            data["content"][platform] = value
    data["edited_at"] = datetime.now(timezone.utc).isoformat()
    with open(src, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    logger.info("Draft %s edited (platforms: %s)", filename, list(updated_content.keys()))
    return data


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
