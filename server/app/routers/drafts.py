import os
import uuid
import logging

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.services.draft_service import upsert_draft, update_draft_status, list_drafts_for_user

logger = logging.getLogger(__name__)

router = APIRouter()

# Local storage dir for draft images (relative to server/ root)
_DRAFT_IMAGE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "draft_images")


def _draft_to_dict(draft) -> dict:
    return {
        "id": draft.id,
        "user_id": draft.user_id,
        "campaign_id": draft.campaign_id,
        "platform": draft.platform,
        "text": draft.text,
        "image_url": draft.image_url,
        "image_local_path": draft.image_local_path,
        "quality_score": draft.quality_score,
        "status": draft.status,
        "iteration": draft.iteration,
        "local_id": draft.local_id,
        "created_at": draft.created_at.isoformat() if draft.created_at else None,
        "updated_at": draft.updated_at.isoformat() if draft.updated_at else None,
    }


class DraftCreate(BaseModel):
    campaign_id: int
    platform: str
    text: str
    iteration: int = 1
    local_id: int | None = None
    image_url: str | None = None
    image_local_path: str | None = None
    quality_score: int | None = None


class DraftUpdate(BaseModel):
    status: str | None = None
    text: str | None = None
    image_url: str | None = None


@router.post("/api/drafts")
async def create_or_update_draft(
    data: DraftCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Daemon uploads a new draft. Idempotent: same (user, campaign, platform, local_id) → update."""
    draft = await upsert_draft(
        db,
        user_id=user.id,
        campaign_id=data.campaign_id,
        platform=data.platform,
        text=data.text,
        iteration=data.iteration,
        local_id=data.local_id,
        image_url=data.image_url,
        image_local_path=data.image_local_path,
        quality_score=data.quality_score,
    )
    return _draft_to_dict(draft)


@router.post("/api/drafts/upload-image")
async def upload_draft_image(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    """Multipart image upload. Saves to data/draft_images/<uuid>.<ext>.
    Returns {url: '/draft-images/<uuid>.<ext>'} for use in subsequent draft create.
    """
    os.makedirs(_DRAFT_IMAGE_DIR, exist_ok=True)

    original_name = file.filename or "image"
    _, ext = os.path.splitext(original_name)
    if not ext:
        # Guess from content_type
        ct = file.content_type or ""
        if "png" in ct:
            ext = ".png"
        elif "gif" in ct:
            ext = ".gif"
        elif "webp" in ct:
            ext = ".webp"
        else:
            ext = ".jpg"

    unique_name = f"{uuid.uuid4().hex}{ext}"
    dest = os.path.join(_DRAFT_IMAGE_DIR, unique_name)

    contents = await file.read()
    with open(dest, "wb") as f:
        f.write(contents)

    url = f"/draft-images/{unique_name}"
    logger.info("Draft image saved: %s (user=%d)", dest, user.id)
    return {"url": url}


@router.get("/api/drafts")
async def list_drafts(
    campaign_id: int | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List drafts for the authenticated user, optionally filtered by campaign_id."""
    drafts = await list_drafts_for_user(db, user_id=user.id, campaign_id=campaign_id)
    return [_draft_to_dict(d) for d in drafts]


@router.patch("/api/drafts/{draft_id}")
async def patch_draft(
    draft_id: int,
    data: DraftUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update status, text, or image of a draft. Validates transitions and ownership."""
    draft = await update_draft_status(
        db,
        draft_id=draft_id,
        user_id=user.id,
        new_status=data.status,
        text=data.text,
        image_url=data.image_url,
    )
    return _draft_to_dict(draft)
