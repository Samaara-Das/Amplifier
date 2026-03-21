"""Trust score management and fraud detection."""

import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.post import Post
from app.models.metric import Metric
from app.models.assignment import CampaignAssignment
from app.models.penalty import Penalty

logger = logging.getLogger(__name__)

# Trust score adjustments
TRUST_EVENTS = {
    "post_verified_live_24h": +1,
    "above_avg_engagement": +2,
    "campaign_completed": +3,
    "user_customized_content": +1,
    "post_deleted_24h": -10,
    "content_flagged": -15,
    "metrics_anomaly": -20,
    "confirmed_fake_metrics": -50,
}


async def adjust_trust(db: AsyncSession, user_id: int, event: str, post_id: int = None,
                       description: str = None) -> int:
    """Adjust a user's trust score based on an event. Returns new score."""
    adjustment = TRUST_EVENTS.get(event, 0)
    if adjustment == 0:
        return 0

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return 0

    old_score = user.trust_score
    new_score = max(0, min(100, old_score + adjustment))
    user.trust_score = new_score

    logger.info("Trust adjusted for user %d: %d -> %d (event: %s)", user_id, old_score, new_score, event)

    # Create penalty for negative events
    if adjustment < 0:
        reason_map = {
            "post_deleted_24h": "content_removed",
            "content_flagged": "platform_violation",
            "metrics_anomaly": "fake_metrics",
            "confirmed_fake_metrics": "fake_metrics",
        }
        penalty = Penalty(
            user_id=user_id,
            post_id=post_id,
            reason=reason_map.get(event, "platform_violation"),
            amount=abs(adjustment) * 0.5,  # $0.50 per trust point lost
            description=description or f"Trust event: {event}",
        )
        db.add(penalty)

    # Ban review if trust drops below 10
    if new_score < 10 and old_score >= 10:
        logger.warning("User %d trust dropped below 10 — flagged for ban review", user_id)
        # Don't auto-ban, just flag (admin reviews via dashboard)

    await db.flush()
    return new_score


async def detect_deletion_fraud(db: AsyncSession) -> list[dict]:
    """Check posts that should be live but may have been deleted.

    Returns list of {user_id, post_id, post_url} for posts to spot-check.
    """
    # Posts that are marked "live" and older than 24h
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    result = await db.execute(
        select(Post)
        .join(CampaignAssignment)
        .where(
            and_(
                Post.status == "live",
                Post.posted_at < cutoff,
            )
        )
        .limit(100)
    )
    posts = result.scalars().all()
    return [{"post_id": p.id, "post_url": p.post_url, "assignment_id": p.assignment_id} for p in posts]


async def detect_metrics_anomalies(db: AsyncSession) -> list[dict]:
    """Flag users whose engagement metrics are statistical outliers.

    Compares each user's avg engagement rate against the overall average
    for the same campaigns. Users >3x the average are flagged.
    """
    flags = []

    # Get avg engagement per user across all their posts
    result = await db.execute(
        select(
            CampaignAssignment.user_id,
            func.avg(Metric.likes + Metric.reposts + Metric.comments).label("avg_engagement"),
            func.count(Metric.id).label("metric_count"),
        )
        .join(Post, Metric.post_id == Post.id)
        .join(CampaignAssignment, Post.assignment_id == CampaignAssignment.id)
        .where(Metric.is_final == True)
        .group_by(CampaignAssignment.user_id)
    )
    user_stats = result.all()

    if len(user_stats) < 5:
        return flags  # Not enough data

    # Calculate overall average
    all_avgs = [s.avg_engagement for s in user_stats if s.avg_engagement]
    if not all_avgs:
        return flags
    overall_avg = sum(all_avgs) / len(all_avgs)

    if overall_avg == 0:
        return flags

    for stat in user_stats:
        if stat.avg_engagement and stat.metric_count >= 3:
            ratio = stat.avg_engagement / overall_avg
            if ratio > 3.0:
                flags.append({
                    "user_id": stat.user_id,
                    "avg_engagement": float(stat.avg_engagement),
                    "overall_avg": float(overall_avg),
                    "ratio": float(ratio),
                    "metric_count": stat.metric_count,
                })
                logger.warning(
                    "Anomaly flag: user %d avg engagement %.1f is %.1fx the average",
                    stat.user_id, stat.avg_engagement, ratio,
                )

    return flags


async def run_trust_check(db: AsyncSession) -> dict:
    """Run all trust/fraud checks. Called periodically by background job."""
    deletion_flags = await detect_deletion_fraud(db)
    anomaly_flags = await detect_metrics_anomalies(db)

    return {
        "deletion_checks": len(deletion_flags),
        "anomaly_flags": len(anomaly_flags),
        "deletions": deletion_flags,
        "anomalies": anomaly_flags,
    }
