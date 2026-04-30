import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.post import Post
from app.models.metric import Metric
from app.models.assignment import CampaignAssignment
from app.schemas.metrics import PostCreate, PostBatchCreate, MetricBatchSubmit

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/posts")
async def register_posts(
    data: PostBatchCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Register posted content URLs with the server."""
    created = []
    skipped_duplicate = 0
    skipped_invalid_assignment = 0
    for post_data in data.posts:
        # Verify assignment belongs to this user
        result = await db.execute(
            select(CampaignAssignment).where(
                and_(
                    CampaignAssignment.id == post_data.assignment_id,
                    CampaignAssignment.user_id == user.id,
                )
            )
        )
        assignment = result.scalar_one_or_none()
        if not assignment:
            skipped_invalid_assignment += 1
            continue

        # Dedup: skip if a post with this URL already exists
        existing = await db.execute(
            select(Post.id).where(Post.post_url == post_data.post_url)
        )
        if existing.scalar_one_or_none() is not None:
            skipped_duplicate += 1
            continue

        post = Post(
            assignment_id=post_data.assignment_id,
            platform=post_data.platform,
            post_url=post_data.post_url,
            content_hash=post_data.content_hash,
            posted_at=post_data.posted_at,
        )
        db.add(post)
        await db.flush()
        created.append({"id": post.id, "platform": post.platform})

    return {
        "created": created,
        "count": len(created),
        "skipped_duplicate": skipped_duplicate,
        "skipped_invalid_assignment": skipped_invalid_assignment,
    }


@router.post("/metrics")
async def submit_metrics(
    data: MetricBatchSubmit,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Batch submit scraped metrics for posts. Deduplicates and rejects deleted posts."""
    accepted = 0
    skipped_deleted = 0
    skipped_duplicate = 0

    for m in data.metrics:
        # Verify post belongs to this user (via assignment)
        result = await db.execute(
            select(Post)
            .join(CampaignAssignment)
            .where(
                and_(
                    Post.id == m.post_id,
                    CampaignAssignment.user_id == user.id,
                )
            )
        )
        post = result.scalar_one_or_none()
        if not post:
            continue

        # Reject metrics for deleted posts — no billing should occur
        if post.status == "deleted":
            skipped_deleted += 1
            continue

        # Duplicate prevention: check if metric with same (post_id, scraped_at) exists
        existing = await db.execute(
            select(Metric.id).where(
                and_(
                    Metric.post_id == m.post_id,
                    Metric.scraped_at == m.scraped_at,
                )
            )
        )
        if existing.scalar_one_or_none() is not None:
            skipped_duplicate += 1
            continue

        metric = Metric(
            post_id=m.post_id,
            impressions=m.impressions,
            likes=m.likes,
            reposts=m.reposts,
            comments=m.comments,
            clicks=m.clicks,
            scraped_at=m.scraped_at,
            is_final=m.is_final,
        )
        db.add(metric)
        accepted += 1

    # Trigger billing on every metric submission (not just final)
    # Metrics grow over time as posts gain engagement, so billing
    # should run incrementally on the latest metrics.
    billing_result = None
    if accepted > 0:
        try:
            from app.services.billing import run_billing_cycle
            billing_result = await run_billing_cycle(db)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("Billing trigger failed: %s", e)

    result = {
        "accepted": accepted,
        "total_submitted": len(data.metrics),
        "skipped_deleted": skipped_deleted,
        "skipped_duplicate": skipped_duplicate,
    }
    if billing_result:
        result["billing"] = billing_result
    return result


class PostStatusUpdate(BaseModel):
    status: str  # "deleted" | "flagged"


@router.patch("/posts/{post_id}/status")
async def update_post_status(
    post_id: int,
    data: PostStatusUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a post's status (e.g. mark as deleted). Voids pending earnings if deleted."""
    if data.status not in ("deleted", "flagged"):
        raise HTTPException(status_code=422, detail="Status must be 'deleted' or 'flagged'")

    # Verify post belongs to this user
    result = await db.execute(
        select(Post)
        .join(CampaignAssignment)
        .where(
            and_(
                Post.id == post_id,
                CampaignAssignment.user_id == user.id,
            )
        )
    )
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    old_status = post.status
    post.status = data.status

    voided_count = 0
    if data.status == "deleted":
        try:
            from app.services.billing import void_earnings_for_post
            voided_count = await void_earnings_for_post(db, post_id)
        except Exception as e:
            logger.warning("Earning voiding failed for post %d: %s", post_id, e)

    return {
        "post_id": post_id,
        "old_status": old_status,
        "new_status": data.status,
        "earnings_voided": voided_count,
    }
