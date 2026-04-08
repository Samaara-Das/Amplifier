"""Helpers for querying the latest metric per post.

After Task #9, is_final was removed from the scraping pipeline.
The latest scrape (highest Metric.id per post) is the billing source of truth.
These helpers replace all Metric.is_final == True filters across the server.
"""

from sqlalchemy import and_, func, select

from app.models.metric import Metric
from app.models.post import Post


def latest_metric_filter():
    """WHERE clause: only the latest metric per post (highest ID = most recent scrape).

    Usage: .where(latest_metric_filter())
    """
    sub = select(func.max(Metric.id)).group_by(Metric.post_id).scalar_subquery()
    return Metric.id.in_(sub)


def latest_metric_join_condition():
    """JOIN condition: Post -> latest Metric only.

    Usage: .outerjoin(Metric, latest_metric_join_condition())
    """
    sub = select(func.max(Metric.id)).group_by(Metric.post_id).scalar_subquery()
    return and_(Metric.post_id == Post.id, Metric.id.in_(sub))
