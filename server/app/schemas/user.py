from pydantic import BaseModel


class UserProfileUpdate(BaseModel):
    platforms: dict | None = None
    follower_counts: dict | None = None
    niche_tags: list[str] | None = None
    audience_region: str | None = None  # us, uk, india, eu, global, etc.
    mode: str | None = None  # full_auto | semi_auto | manual
    device_fingerprint: str | None = None


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


class EarningsSummary(BaseModel):
    total_earned: float
    current_balance: float
    pending: float  # earned but not yet paid out
    per_campaign: list[dict]  # [{campaign_id, campaign_title, earned}]
