from pydantic import BaseModel


class UserProfileUpdate(BaseModel):
    platforms: dict | None = None
    follower_counts: dict | None = None
    niche_tags: list[str] | None = None
    audience_region: str | None = None  # us, uk, india, eu, global, etc.
    mode: str | None = None  # full_auto | semi_auto | manual
    device_fingerprint: str | None = None
    scraped_profiles: dict | None = None  # Per-platform scraped summary data
    ai_detected_niches: list[str] | None = None  # AI-classified niches from content


class UserProfileResponse(BaseModel):
    id: int
    email: str
    platforms: dict
    follower_counts: dict
    niche_tags: list[str]
    audience_region: str
    trust_score: int
    mode: str
    earnings_balance: float
    total_earned: float
    status: str

    model_config = {"from_attributes": True}


class CampaignEarning(BaseModel):
    campaign_id: int
    campaign_title: str
    posts: int
    impressions: int
    engagement: int
    earned: float
    status: str


class PayoutHistoryEntry(BaseModel):
    id: int
    amount: float
    status: str
    requested_at: str


class EarningsSummary(BaseModel):
    total_earned: float
    current_balance: float
    pending: float
    per_campaign: list[CampaignEarning]
    per_platform: dict[str, float]
    payout_history: list[PayoutHistoryEntry]


class PayoutRequest(BaseModel):
    amount: float


class PayoutResponse(BaseModel):
    payout_id: int
    amount: float
    status: str
    new_balance: float
