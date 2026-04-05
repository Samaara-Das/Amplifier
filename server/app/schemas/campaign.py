from datetime import datetime
from pydantic import BaseModel


class PayoutRules(BaseModel):
    rate_per_1k_impressions: float = 0.50
    rate_per_like: float = 0.01
    rate_per_repost: float = 0.05
    rate_per_click: float = 0.10


class Targeting(BaseModel):
    min_followers: dict[str, int] = {}  # {"x": 100, "linkedin": 50}
    min_engagement: float = 0.0  # Minimum avg engagement rate (0.0 = no filter)
    niche_tags: list[str] = []
    required_platforms: list[str] = []
    target_regions: list[str] = []  # ["us", "uk", "eu", ...]


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
    max_users: int | None = None
    # Phase C additions
    campaign_goal: str = "brand_awareness"
    campaign_type: str = "ai_generated"
    tone: str | None = None
    preferred_formats: dict = {}
    disclaimer_text: str | None = None


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
    screening_status: str = "pending"
    start_date: datetime
    end_date: datetime
    created_at: datetime
    budget_alert_sent: bool = False
    campaign_version: int = 1
    max_users: int | None = None
    screening_warning: str | None = None
    # Phase C additions
    campaign_goal: str | None = None
    campaign_type: str | None = None
    tone: str | None = None
    preferred_formats: dict = {}
    disclaimer_text: str | None = None

    model_config = {"from_attributes": True}


class BudgetTopUp(BaseModel):
    amount: float


# ── Repost Campaign schemas (must be before CampaignBrief) ─────

class CampaignPostCreate(BaseModel):
    platform: str
    content: str
    image_url: str | None = None
    post_order: int = 1
    scheduled_offset_hours: int = 0


class CampaignPostResponse(BaseModel):
    id: int
    platform: str
    content: str
    image_url: str | None
    post_order: int
    scheduled_offset_hours: int

    model_config = {"from_attributes": True}


class CampaignBrief(BaseModel):
    """What the user app receives -- campaign info needed for content generation."""
    campaign_id: int
    assignment_id: int
    title: str
    brief: str
    assets: dict
    content_guidance: str | None
    payout_rules: dict
    payout_multiplier: float
    company_name: str | None = None
    # Phase C additions
    campaign_type: str = "ai_generated"
    campaign_goal: str | None = None
    tone: str | None = None
    preferred_formats: dict = {}
    disclaimer_text: str | None = None
    # Repost campaign: pre-written posts
    campaign_posts: list[CampaignPostResponse] = []

    model_config = {"from_attributes": True}


# ── AI Wizard schemas ─────────────────────────────────────────────


class WizardRequest(BaseModel):
    """Input for the AI campaign creation wizard."""
    product_description: str
    campaign_goal: str  # brand_awareness | product_launch | event_promotion | lead_generation
    product_name: str | None = None
    product_features: str | None = None
    company_urls: list[str] = []
    target_niches: list[str] = []
    target_regions: list[str] = []
    required_platforms: list[str] = []
    min_followers: dict[str, int] = {}
    min_engagement: float = 0.0
    max_users: int | None = None
    tone: str | None = None  # Legacy — kept for backward compat, not used
    must_include: list[str] = []
    must_avoid: list[str] = []
    budget_range: dict[str, float] | None = None  # {"min": 200, "max": 500}
    start_date: str | None = None
    end_date: str | None = None


class ReachEstimateRequest(BaseModel):
    """Input for pre-creation reach estimation."""
    target_niches: list[str] = []
    target_regions: list[str] = []
    required_platforms: list[str] = []
    min_followers: dict[str, int] = {}



# (CampaignPostCreate and CampaignPostResponse defined above CampaignBrief)
