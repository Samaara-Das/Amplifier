from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.post import Post
from app.models.metric import Metric
from app.models.assignment import CampaignAssignment
from app.schemas.metrics import PostCreate, PostBatchCreate, MetricBatchSubmit

router = APIRouter()


@router.post("/posts")
async def register_posts(
    data: PostBatchCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Register posted content URLs with the server."""
    created = []
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
            continue  # Skip invalid assignments silently

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

    return {"created": created, "count": len(created)}


@router.post("/metrics")
async def submit_metrics(
    data: MetricBatchSubmit,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Batch submit scraped metrics for posts."""
    accepted = 0
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

    # Trigger billing for any final metrics just submitted
    billing_result = None
    has_final = any(m.is_final for m in data.metrics)
    if has_final and accepted > 0:
        try:
            from app.services.billing import run_billing_cycle
            billing_result = await run_billing_cycle(db)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("Billing trigger failed: %s", e)

    result = {"accepted": accepted, "total_submitted": len(data.metrics)}
    if billing_result:
        result["billing"] = billing_result
    return result
