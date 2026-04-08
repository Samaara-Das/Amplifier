from datetime import datetime
from pydantic import BaseModel


class PostCreate(BaseModel):
    assignment_id: int
    platform: str  # x | linkedin | facebook | reddit | tiktok | instagram
    post_url: str
    content_hash: str
    posted_at: datetime


class MetricSubmission(BaseModel):
    post_id: int
    impressions: int = 0
    likes: int = 0
    reposts: int = 0
    comments: int = 0
    clicks: int = 0
    scraped_at: datetime
    is_final: bool = False  # Deprecated: no longer used. Kept for backward compat.


class MetricBatchSubmit(BaseModel):
    metrics: list[MetricSubmission]


class PostBatchCreate(BaseModel):
    posts: list[PostCreate]
