"""Business logic for Draft model: upsert, status transitions, listing."""

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.draft import Draft

# Valid status transitions:
# pending → any (approved, rejected, posted)
# approved → rejected, posted
# posted is terminal (no outbound transitions)
# rejected → pending (allow restore) — not in spec but not blocked
_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"approved", "rejected", "posted"},
    "approved": {"rejected", "posted"},
    "rejected": {"pending", "approved"},
    "posted": set(),  # terminal
}


async def upsert_draft(
    db: AsyncSession,
    *,
    user_id: int,
    campaign_id: int,
    platform: str,
    text: str,
    iteration: int,
    local_id: int | None = None,
    image_url: str | None = None,
    image_local_path: str | None = None,
    quality_score: int | None = None,
) -> Draft:
    """Create or update a Draft.

    If local_id is not None and a Draft with (user_id, campaign_id, platform, local_id)
    already exists, update it and return it. Otherwise insert a new row.
    """
    existing: Draft | None = None
    if local_id is not None:
        result = await db.execute(
            select(Draft).where(
                and_(
                    Draft.user_id == user_id,
                    Draft.campaign_id == campaign_id,
                    Draft.platform == platform,
                    Draft.local_id == local_id,
                )
            )
        )
        existing = result.scalar_one_or_none()

    if existing is not None:
        existing.text = text
        existing.iteration = iteration
        existing.image_url = image_url
        existing.image_local_path = image_local_path
        existing.quality_score = quality_score
        existing.updated_at = datetime.now(timezone.utc)
        await db.flush()
        return existing

    draft = Draft(
        user_id=user_id,
        campaign_id=campaign_id,
        platform=platform,
        text=text,
        iteration=iteration,
        local_id=local_id,
        image_url=image_url,
        image_local_path=image_local_path,
        quality_score=quality_score,
        status="pending",
    )
    db.add(draft)
    await db.flush()
    return draft


async def update_draft_status(
    db: AsyncSession,
    *,
    draft_id: int,
    user_id: int,
    new_status: str | None = None,
    text: str | None = None,
    image_url: str | None = None,
) -> Draft:
    """Update a draft's status/text/image. Enforces ownership and valid transitions."""
    result = await db.execute(select(Draft).where(Draft.id == draft_id))
    draft = result.scalar_one_or_none()
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    if draft.user_id != user_id:
        raise HTTPException(status_code=403, detail="Not your draft")

    if new_status is not None:
        allowed = _ALLOWED_TRANSITIONS.get(draft.status, set())
        if new_status not in allowed:
            raise HTTPException(
                status_code=422,
                detail=f"Cannot transition draft from '{draft.status}' to '{new_status}'",
            )
        draft.status = new_status

    if text is not None:
        draft.text = text
    if image_url is not None:
        draft.image_url = image_url

    draft.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return draft


async def list_drafts_for_user(
    db: AsyncSession,
    *,
    user_id: int,
    campaign_id: int | None = None,
) -> list[Draft]:
    """List all drafts for a user, optionally filtered by campaign."""
    conditions = [Draft.user_id == user_id]
    if campaign_id is not None:
        conditions.append(Draft.campaign_id == campaign_id)
    result = await db.execute(select(Draft).where(and_(*conditions)))
    return list(result.scalars().all())
