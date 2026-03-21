from datetime import datetime
from pydantic import BaseModel


class PayoutRules(BaseModel):
    rate_per_1k_impressions: float = 0.50
    rate_per_like: float = 0.01
    rate_per_repost: float = 0.05
    rate_per_click: float = 0.10


class Targeting(BaseModel):
    min_followers: dict[str, int] = {}  # {"x": 100, "linkedin": 50}
    niche_tags: list[str] = []
    required_platforms: list[str] = []


class CampaignCreate(BaseModel):
    title: str
    brief: str
    assets: dict = {}
    budget_total: float
    payout_rules: PayoutRules
    targeting: Targeting = Targeting()
    content_guidance: str | None = None
    penalty_rules: dict = {}
    start_date: datetime
    end_date: datetime


class CampaignUpdate(BaseModel):
    title: str | None = None
    brief: str | None = None
    assets: dict | None = None
    content_guidance: str | None = None
    status: str | None = None  # pause or cancel


class CampaignResponse(BaseModel):
    id: int
    company_id: int
    title: str
    brief: str
    assets: dict
    budget_total: float
    budget_remaining: float
    payout_rules: dict
    targeting: dict
    content_guidance: str | None
    status: str
    start_date: datetime
    end_date: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class CampaignBrief(BaseModel):
    """What the user app receives — campaign info needed for content generation."""
    campaign_id: int
    assignment_id: int
    title: str
    brief: str
    assets: dict
    content_guidance: str | None
    payout_rules: dict
    payout_multiplier: float

    model_config = {"from_attributes": True}
