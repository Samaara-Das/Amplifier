"""Tests for database schema v2 migration.

Covers:
- Server model field additions and defaults (column metadata checks)
- New CampaignInvitationLog model
- New ContentScreeningLog model
- Local DB new tables (scraped_profile, post_schedule)
- Local DB local_campaign invitation fields
- Async DB integration round-trips
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest
import pytest_asyncio

# ── Path setup ────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(ROOT / "scripts"))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def _server_env(monkeypatch):
    """Point server to an in-memory SQLite DB for testing."""
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    from app.core import config
    config.get_settings.cache_clear()


@pytest.fixture
def _local_db(tmp_path, monkeypatch):
    """Temp local DB for local_db tests."""
    db_path = tmp_path / "test_v2.db"
    monkeypatch.setattr("utils.local_db.DB_PATH", db_path)
    from utils.local_db import init_db
    init_db()


# ---------------------------------------------------------------------------
# Helper: get column default from SQLAlchemy column metadata
# ---------------------------------------------------------------------------

def _col_default(model_cls, col_name):
    """Return the default.arg from a mapped column, handling callables."""
    col = model_cls.__table__.c[col_name]
    if col.default is not None:
        d = col.default.arg
        if callable(d):
            # SQLAlchemy wraps callables; try no-arg first, then return the callable itself
            try:
                return d()
            except TypeError:
                return d  # Return the callable (e.g., dict, list) for identity check
        return d
    return None


# ===================================================================
# Subtask 1: CampaignAssignment model updates
# ===================================================================

class TestCampaignAssignmentModel:

    def test_status_default_is_pending_invitation(self):
        from app.models.assignment import CampaignAssignment
        assert _col_default(CampaignAssignment, "status") == "pending_invitation"

    def test_payout_multiplier_default_is_1_0(self):
        from app.models.assignment import CampaignAssignment
        assert float(_col_default(CampaignAssignment, "payout_multiplier")) == 1.0

    def test_invited_at_column_exists(self):
        from app.models.assignment import CampaignAssignment
        assert "invited_at" in CampaignAssignment.__table__.c

    def test_responded_at_column_exists(self):
        from app.models.assignment import CampaignAssignment
        assert "responded_at" in CampaignAssignment.__table__.c

    def test_expires_at_column_exists(self):
        from app.models.assignment import CampaignAssignment
        assert "expires_at" in CampaignAssignment.__table__.c

    def test_responded_at_nullable(self):
        from app.models.assignment import CampaignAssignment
        col = CampaignAssignment.__table__.c.responded_at
        assert col.nullable is True

    def test_expires_at_nullable(self):
        from app.models.assignment import CampaignAssignment
        col = CampaignAssignment.__table__.c.expires_at
        assert col.nullable is True

    def test_composite_index_user_status_exists(self):
        from app.models.assignment import CampaignAssignment
        table = CampaignAssignment.__table__
        index_names = {idx.name for idx in table.indexes}
        assert "ix_assignment_user_status" in index_names

    def test_expires_at_index_exists(self):
        from app.models.assignment import CampaignAssignment
        table = CampaignAssignment.__table__
        index_names = {idx.name for idx in table.indexes}
        assert "ix_assignment_expires_at" in index_names

    def test_existing_columns_preserved(self):
        from app.models.assignment import CampaignAssignment
        table = CampaignAssignment.__table__
        required = {"id", "campaign_id", "user_id", "status", "content_mode",
                     "payout_multiplier", "assigned_at", "updated_at"}
        assert required.issubset(set(table.c.keys()))


# ===================================================================
# Subtask 2: User model updates
# ===================================================================

class TestUserModel:

    def test_scraped_profiles_column_exists(self):
        from app.models.user import User
        assert "scraped_profiles" in User.__table__.c

    def test_scraped_profiles_default_empty_dict(self):
        from app.models.user import User
        default = _col_default(User, "scraped_profiles")
        assert default is not None and (default == {} or callable(default))

    def test_ai_detected_niches_column_exists(self):
        from app.models.user import User
        assert "ai_detected_niches" in User.__table__.c

    def test_ai_detected_niches_default_empty_list(self):
        from app.models.user import User
        default = _col_default(User, "ai_detected_niches")
        assert default is not None and (default == [] or callable(default))

    def test_last_scraped_at_column_exists(self):
        from app.models.user import User
        assert "last_scraped_at" in User.__table__.c

    def test_last_scraped_at_nullable(self):
        from app.models.user import User
        col = User.__table__.c.last_scraped_at
        assert col.nullable is True

    def test_existing_columns_preserved(self):
        from app.models.user import User
        table = User.__table__
        required = {"id", "email", "password_hash", "platforms", "follower_counts",
                     "niche_tags", "audience_region", "trust_score", "mode",
                     "earnings_balance", "total_earned", "status"}
        assert required.issubset(set(table.c.keys()))


# ===================================================================
# Subtask 3: Campaign model updates
# ===================================================================

class TestCampaignModel:

    def test_company_urls_column_exists(self):
        from app.models.campaign import Campaign
        assert "company_urls" in Campaign.__table__.c

    def test_company_urls_default(self):
        from app.models.campaign import Campaign
        default = _col_default(Campaign, "company_urls")
        assert default is not None and (default == [] or callable(default))

    def test_ai_generated_brief_column_exists(self):
        from app.models.campaign import Campaign
        assert "ai_generated_brief" in Campaign.__table__.c

    def test_ai_generated_brief_default_false(self):
        from app.models.campaign import Campaign
        assert _col_default(Campaign, "ai_generated_brief") is False

    def test_budget_exhaustion_action_column_exists(self):
        from app.models.campaign import Campaign
        assert "budget_exhaustion_action" in Campaign.__table__.c

    def test_budget_exhaustion_action_default(self):
        from app.models.campaign import Campaign
        assert _col_default(Campaign, "budget_exhaustion_action") == "auto_pause"

    def test_invitation_count_default_zero(self):
        from app.models.campaign import Campaign
        assert _col_default(Campaign, "invitation_count") == 0

    def test_accepted_count_default_zero(self):
        from app.models.campaign import Campaign
        assert _col_default(Campaign, "accepted_count") == 0

    def test_rejected_count_default_zero(self):
        from app.models.campaign import Campaign
        assert _col_default(Campaign, "rejected_count") == 0

    def test_expired_count_default_zero(self):
        from app.models.campaign import Campaign
        assert _col_default(Campaign, "expired_count") == 0

    def test_existing_columns_preserved(self):
        from app.models.campaign import Campaign
        table = Campaign.__table__
        required = {"id", "company_id", "title", "brief", "assets",
                     "budget_total", "budget_remaining", "payout_rules",
                     "targeting", "content_guidance", "penalty_rules",
                     "status", "start_date", "end_date"}
        assert required.issubset(set(table.c.keys()))


# ===================================================================
# Subtask 4: CampaignInvitationLog model
# ===================================================================

class TestCampaignInvitationLogModel:

    def test_model_exists(self):
        from app.models.invitation_log import CampaignInvitationLog
        assert CampaignInvitationLog.__tablename__ == "campaign_invitation_log"

    def test_columns_exist(self):
        from app.models.invitation_log import CampaignInvitationLog
        table = CampaignInvitationLog.__table__
        required = {"id", "campaign_id", "user_id", "event", "metadata", "created_at"}
        assert required.issubset(set(table.c.keys()))

    def test_event_metadata_attribute_maps_to_metadata_column(self):
        from app.models.invitation_log import CampaignInvitationLog
        # Python attribute is event_metadata, DB column is metadata
        assert hasattr(CampaignInvitationLog, "event_metadata")
        assert "metadata" in CampaignInvitationLog.__table__.c

    def test_composite_index_campaign_user(self):
        from app.models.invitation_log import CampaignInvitationLog
        table = CampaignInvitationLog.__table__
        index_names = {idx.name for idx in table.indexes}
        assert "ix_invitation_log_campaign_user" in index_names

    def test_campaign_id_indexed(self):
        from app.models.invitation_log import CampaignInvitationLog
        col = CampaignInvitationLog.__table__.c.campaign_id
        assert col.index is True

    def test_user_id_indexed(self):
        from app.models.invitation_log import CampaignInvitationLog
        col = CampaignInvitationLog.__table__.c.user_id
        assert col.index is True

    def test_import_from_models_package(self):
        from app.models import CampaignInvitationLog
        assert CampaignInvitationLog is not None

    def test_campaign_id_foreign_key(self):
        from app.models.invitation_log import CampaignInvitationLog
        col = CampaignInvitationLog.__table__.c.campaign_id
        fk_targets = {fk.target_fullname for fk in col.foreign_keys}
        assert "campaigns.id" in fk_targets

    def test_user_id_foreign_key(self):
        from app.models.invitation_log import CampaignInvitationLog
        col = CampaignInvitationLog.__table__.c.user_id
        fk_targets = {fk.target_fullname for fk in col.foreign_keys}
        assert "users.id" in fk_targets


# ===================================================================
# Subtask 5: ContentScreeningLog model
# ===================================================================

class TestContentScreeningLogModel:

    def test_model_exists(self):
        from app.models.screening_log import ContentScreeningLog
        assert ContentScreeningLog.__tablename__ == "content_screening_log"

    def test_columns_exist(self):
        from app.models.screening_log import ContentScreeningLog
        table = ContentScreeningLog.__table__
        required = {"id", "campaign_id", "flagged", "flagged_keywords",
                     "screening_categories", "reviewed_by_admin",
                     "review_result", "review_notes", "created_at"}
        assert required.issubset(set(table.c.keys()))

    def test_flagged_default_false(self):
        from app.models.screening_log import ContentScreeningLog
        assert _col_default(ContentScreeningLog, "flagged") is False

    def test_reviewed_by_admin_default_false(self):
        from app.models.screening_log import ContentScreeningLog
        assert _col_default(ContentScreeningLog, "reviewed_by_admin") is False

    def test_review_result_nullable(self):
        from app.models.screening_log import ContentScreeningLog
        col = ContentScreeningLog.__table__.c.review_result
        assert col.nullable is True

    def test_review_notes_nullable(self):
        from app.models.screening_log import ContentScreeningLog
        col = ContentScreeningLog.__table__.c.review_notes
        assert col.nullable is True

    def test_campaign_id_unique(self):
        from app.models.screening_log import ContentScreeningLog
        col = ContentScreeningLog.__table__.c.campaign_id
        assert col.unique is True

    def test_review_queue_index_exists(self):
        from app.models.screening_log import ContentScreeningLog
        table = ContentScreeningLog.__table__
        index_names = {idx.name for idx in table.indexes}
        assert "ix_screening_review_queue" in index_names

    def test_campaign_id_foreign_key(self):
        from app.models.screening_log import ContentScreeningLog
        col = ContentScreeningLog.__table__.c.campaign_id
        fk_targets = {fk.target_fullname for fk in col.foreign_keys}
        assert "campaigns.id" in fk_targets

    def test_import_from_models_package(self):
        from app.models import ContentScreeningLog
        assert ContentScreeningLog is not None


# ===================================================================
# Subtask 6: Local DB — scraped_profile table
# ===================================================================

class TestLocalDbScrapedProfile:

    def test_upsert_scraped_profile(self, _local_db):
        from utils.local_db import upsert_scraped_profile, get_scraped_profile
        upsert_scraped_profile(
            platform="x",
            follower_count=1500,
            following_count=420,
            bio="Trading insights & tech",
            display_name="John Doe",
            profile_pic_url="https://example.com/pic.jpg",
            recent_posts=json.dumps([{"text": "hello", "likes": 10}]),
            engagement_rate=3.2,
            posting_frequency=1.4,
            ai_niches=json.dumps(["finance", "tech"]),
        )
        profile = get_scraped_profile("x")
        assert profile is not None
        assert profile["follower_count"] == 1500
        assert profile["following_count"] == 420
        assert profile["bio"] == "Trading insights & tech"
        assert profile["display_name"] == "John Doe"
        assert profile["engagement_rate"] == 3.2
        assert profile["posting_frequency"] == 1.4

    def test_upsert_overwrites_existing(self, _local_db):
        from utils.local_db import upsert_scraped_profile, get_scraped_profile
        upsert_scraped_profile(
            platform="x", follower_count=100, following_count=50,
            bio="old", display_name="Old", profile_pic_url=None,
            recent_posts="[]", engagement_rate=1.0, posting_frequency=0.5,
            ai_niches="[]",
        )
        upsert_scraped_profile(
            platform="x", follower_count=200, following_count=100,
            bio="new", display_name="New", profile_pic_url=None,
            recent_posts="[]", engagement_rate=2.0, posting_frequency=1.0,
            ai_niches="[]",
        )
        profile = get_scraped_profile("x")
        assert profile["follower_count"] == 200
        assert profile["bio"] == "new"

    def test_get_all_scraped_profiles(self, _local_db):
        from utils.local_db import upsert_scraped_profile, get_all_scraped_profiles
        upsert_scraped_profile(
            platform="x", follower_count=100, following_count=50,
            bio="bio", display_name="X User", profile_pic_url=None,
            recent_posts="[]", engagement_rate=1.0, posting_frequency=0.5,
            ai_niches="[]",
        )
        upsert_scraped_profile(
            platform="linkedin", follower_count=500, following_count=200,
            bio="bio2", display_name="LI User", profile_pic_url=None,
            recent_posts="[]", engagement_rate=5.0, posting_frequency=0.3,
            ai_niches="[]",
        )
        profiles = get_all_scraped_profiles()
        assert len(profiles) == 2
        platforms = {p["platform"] for p in profiles}
        assert platforms == {"x", "linkedin"}

    def test_get_nonexistent_profile_returns_none(self, _local_db):
        from utils.local_db import get_scraped_profile
        assert get_scraped_profile("tiktok") is None

    def test_platform_uniqueness(self, _local_db):
        """Platform column is UNIQUE — upsert should handle gracefully."""
        from utils.local_db import upsert_scraped_profile, get_all_scraped_profiles
        upsert_scraped_profile(
            platform="reddit", follower_count=100, following_count=50,
            bio="bio", display_name="User", profile_pic_url=None,
            recent_posts="[]", engagement_rate=1.0, posting_frequency=0.5,
            ai_niches="[]",
        )
        upsert_scraped_profile(
            platform="reddit", follower_count=200, following_count=100,
            bio="bio2", display_name="User2", profile_pic_url=None,
            recent_posts="[]", engagement_rate=2.0, posting_frequency=1.0,
            ai_niches="[]",
        )
        profiles = get_all_scraped_profiles()
        reddit_profiles = [p for p in profiles if p["platform"] == "reddit"]
        assert len(reddit_profiles) == 1


# ===================================================================
# Subtask 6: Local DB — post_schedule table
# ===================================================================

class TestLocalDbPostSchedule:

    def test_add_scheduled_post(self, _local_db):
        from utils.local_db import (
            upsert_campaign, add_scheduled_post, get_scheduled_posts,
        )
        upsert_campaign({
            "campaign_id": 1, "assignment_id": 10,
            "title": "Test", "brief": "Brief",
        })
        post_id = add_scheduled_post(
            campaign_server_id=1,
            platform="x",
            scheduled_at="2026-03-25T10:00:00Z",
            content="Hello world",
            image_path=None,
        )
        assert post_id > 0
        posts = get_scheduled_posts(status="queued")
        assert len(posts) >= 1
        assert posts[0]["platform"] == "x"
        assert posts[0]["content"] == "Hello world"
        assert posts[0]["status"] == "queued"

    def test_update_schedule_status(self, _local_db):
        from utils.local_db import (
            upsert_campaign, add_scheduled_post, update_schedule_status,
            get_scheduled_posts,
        )
        upsert_campaign({
            "campaign_id": 2, "assignment_id": 20,
            "title": "Test2", "brief": "Brief2",
        })
        post_id = add_scheduled_post(
            campaign_server_id=2, platform="linkedin",
            scheduled_at="2026-03-25T12:00:00Z",
            content="LI post",
        )
        update_schedule_status(post_id, "posted")
        posts = get_scheduled_posts(status="posted")
        assert len(posts) >= 1
        assert posts[0]["id"] == post_id

    def test_update_schedule_status_with_error(self, _local_db):
        from utils.local_db import (
            upsert_campaign, add_scheduled_post, update_schedule_status,
            get_scheduled_posts,
        )
        upsert_campaign({
            "campaign_id": 3, "assignment_id": 30,
            "title": "Test3", "brief": "Brief3",
        })
        post_id = add_scheduled_post(
            campaign_server_id=3, platform="facebook",
            scheduled_at="2026-03-25T14:00:00Z",
            content="FB post",
        )
        update_schedule_status(post_id, "failed", error_message="Session expired")
        posts = get_scheduled_posts(status="failed")
        assert len(posts) >= 1
        assert posts[0]["error_message"] == "Session expired"

    def test_get_scheduled_posts_all(self, _local_db):
        from utils.local_db import upsert_campaign, add_scheduled_post, get_scheduled_posts
        upsert_campaign({
            "campaign_id": 4, "assignment_id": 40,
            "title": "Test4", "brief": "Brief4",
        })
        add_scheduled_post(
            campaign_server_id=4, platform="x",
            scheduled_at="2026-03-25T10:00:00Z", content="A",
        )
        add_scheduled_post(
            campaign_server_id=4, platform="linkedin",
            scheduled_at="2026-03-25T11:00:00Z", content="B",
        )
        all_posts = get_scheduled_posts()
        assert len(all_posts) >= 2


# ===================================================================
# Subtask 6: Local DB — local_campaign invitation fields
# ===================================================================

class TestLocalCampaignInvitationFields:

    def test_upsert_campaign_with_invitation_fields(self, _local_db):
        from utils.local_db import upsert_campaign, get_campaign
        upsert_campaign({
            "campaign_id": 100, "assignment_id": 200,
            "title": "Invite Test", "brief": "Brief",
            "invitation_status": "pending_invitation",
            "invited_at": "2026-03-24T10:00:00Z",
            "expires_at": "2026-03-27T10:00:00Z",
        })
        c = get_campaign(100)
        assert c is not None
        assert c["invitation_status"] == "pending_invitation"
        assert c["invited_at"] == "2026-03-24T10:00:00Z"
        assert c["expires_at"] == "2026-03-27T10:00:00Z"
        assert c["responded_at"] is None

    def test_update_invitation_status(self, _local_db):
        from utils.local_db import upsert_campaign, update_invitation_status, get_campaign
        upsert_campaign({
            "campaign_id": 101, "assignment_id": 201,
            "title": "Accept Test", "brief": "Brief",
            "invitation_status": "pending_invitation",
            "invited_at": "2026-03-24T10:00:00Z",
            "expires_at": "2026-03-27T10:00:00Z",
        })
        update_invitation_status(101, "accepted", "2026-03-24T12:00:00Z")
        c = get_campaign(101)
        assert c["invitation_status"] == "accepted"
        assert c["responded_at"] == "2026-03-24T12:00:00Z"

    def test_get_campaigns_by_invitation_status(self, _local_db):
        from utils.local_db import upsert_campaign, get_campaigns_by_invitation_status
        upsert_campaign({
            "campaign_id": 102, "assignment_id": 202,
            "title": "Pending 1", "brief": "Brief",
            "invitation_status": "pending_invitation",
            "invited_at": "2026-03-24T10:00:00Z",
            "expires_at": "2026-03-27T10:00:00Z",
        })
        upsert_campaign({
            "campaign_id": 103, "assignment_id": 203,
            "title": "Accepted 1", "brief": "Brief",
            "invitation_status": "accepted",
            "invited_at": "2026-03-24T10:00:00Z",
            "expires_at": "2026-03-27T10:00:00Z",
        })
        pending = get_campaigns_by_invitation_status("pending_invitation")
        assert len(pending) == 1
        assert pending[0]["title"] == "Pending 1"

    def test_default_invitation_status(self, _local_db):
        """When no invitation fields provided, defaults apply."""
        from utils.local_db import upsert_campaign, get_campaign
        upsert_campaign({
            "campaign_id": 104, "assignment_id": 204,
            "title": "No Invite", "brief": "Brief",
        })
        c = get_campaign(104)
        assert c["invitation_status"] == "pending_invitation"


# ===================================================================
# Subtask 7: Migration endpoint
# ===================================================================

class TestMigrationRouter:

    def test_migration_router_importable(self):
        """The migration router module can be imported."""
        from app.routers.migration_v2 import router
        assert router is not None

    def test_migration_endpoint_exists(self):
        """The migration router has the /run-v2-migration endpoint."""
        from app.routers.migration_v2 import router
        paths = [route.path for route in router.routes]
        assert "/run-v2-migration" in paths


# ===================================================================
# Subtask 8: Async DB integration tests (round-trips through DB)
# ===================================================================

@pytest_asyncio.fixture
async def _async_db(_server_env):
    """Create and tear down all tables in-memory for async tests."""
    from app.core.database import engine, Base
    import app.models  # noqa: F401 — register all models
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.mark.asyncio
class TestServerDbIntegration:
    """Full async DB round-trip tests using in-memory SQLite."""

    async def test_create_invitation_log(self, _async_db):
        from app.core.database import async_session
        from app.models.invitation_log import CampaignInvitationLog
        from app.models.user import User
        from app.models.campaign import Campaign
        from app.models.company import Company

        async with async_session() as session:
            company = Company(
                name="Test Co", email="test@co.com",
                password_hash="hash", balance=1000,
            )
            session.add(company)
            await session.flush()

            campaign = Campaign(
                company_id=company.id, title="Test Campaign",
                brief="Brief", budget_total=500, budget_remaining=500,
                payout_rules={}, start_date=datetime.now(timezone.utc),
                end_date=datetime.now(timezone.utc),
            )
            session.add(campaign)
            await session.flush()

            user = User(email="user@test.com", password_hash="hash")
            session.add(user)
            await session.flush()

            log = CampaignInvitationLog(
                campaign_id=campaign.id,
                user_id=user.id,
                event="sent",
                event_metadata={"batch": 1},
            )
            session.add(log)
            await session.commit()

            from sqlalchemy import select
            result = await session.execute(
                select(CampaignInvitationLog).where(
                    CampaignInvitationLog.campaign_id == campaign.id
                )
            )
            logs = result.scalars().all()
            assert len(logs) == 1
            assert logs[0].event == "sent"
            assert logs[0].event_metadata == {"batch": 1}

    async def test_create_screening_log(self, _async_db):
        from app.core.database import async_session
        from app.models.screening_log import ContentScreeningLog
        from app.models.campaign import Campaign
        from app.models.company import Company

        async with async_session() as session:
            company = Company(
                name="Test Co2", email="test2@co.com",
                password_hash="hash", balance=1000,
            )
            session.add(company)
            await session.flush()

            campaign = Campaign(
                company_id=company.id, title="Screened Campaign",
                brief="Suspicious brief", budget_total=500,
                budget_remaining=500, payout_rules={},
                start_date=datetime.now(timezone.utc),
                end_date=datetime.now(timezone.utc),
            )
            session.add(campaign)
            await session.flush()

            screening = ContentScreeningLog(
                campaign_id=campaign.id,
                flagged=True,
                flagged_keywords=["get rich quick"],
                screening_categories=["financial_fraud"],
            )
            session.add(screening)
            await session.commit()

            from sqlalchemy import select
            result = await session.execute(
                select(ContentScreeningLog).where(
                    ContentScreeningLog.campaign_id == campaign.id
                )
            )
            logs = result.scalars().all()
            assert len(logs) == 1
            assert logs[0].flagged is True
            assert logs[0].flagged_keywords == ["get rich quick"]
            assert logs[0].reviewed_by_admin is False

    async def test_screening_log_campaign_unique_constraint(self, _async_db):
        """Only one screening log per campaign."""
        from app.core.database import async_session
        from app.models.screening_log import ContentScreeningLog
        from app.models.campaign import Campaign
        from app.models.company import Company
        from sqlalchemy.exc import IntegrityError

        async with async_session() as session:
            company = Company(
                name="Unique Co", email="unique@co.com",
                password_hash="hash", balance=1000,
            )
            session.add(company)
            await session.flush()

            campaign = Campaign(
                company_id=company.id, title="Unique Test",
                brief="Brief", budget_total=500, budget_remaining=500,
                payout_rules={},
                start_date=datetime.now(timezone.utc),
                end_date=datetime.now(timezone.utc),
            )
            session.add(campaign)
            await session.flush()

            s1 = ContentScreeningLog(campaign_id=campaign.id, flagged=False)
            session.add(s1)
            await session.flush()

            s2 = ContentScreeningLog(campaign_id=campaign.id, flagged=True)
            session.add(s2)
            with pytest.raises(IntegrityError):
                await session.flush()

    async def test_campaign_new_fields_persist(self, _async_db):
        from app.core.database import async_session
        from app.models.campaign import Campaign
        from app.models.company import Company

        async with async_session() as session:
            company = Company(
                name="Field Test Co", email="field@co.com",
                password_hash="hash", balance=1000,
            )
            session.add(company)
            await session.flush()

            campaign = Campaign(
                company_id=company.id, title="V2 Campaign",
                brief="Brief", budget_total=500, budget_remaining=500,
                payout_rules={},
                start_date=datetime.now(timezone.utc),
                end_date=datetime.now(timezone.utc),
                company_urls=["https://acme.com"],
                ai_generated_brief=True,
                budget_exhaustion_action="auto_complete",
                invitation_count=10,
                accepted_count=5,
            )
            session.add(campaign)
            await session.commit()

            from sqlalchemy import select
            result = await session.execute(
                select(Campaign).where(Campaign.id == campaign.id)
            )
            c = result.scalar_one()
            assert c.company_urls == ["https://acme.com"]
            assert c.ai_generated_brief is True
            assert c.budget_exhaustion_action == "auto_complete"
            assert c.invitation_count == 10
            assert c.accepted_count == 5

    async def test_campaign_defaults_persist(self, _async_db):
        """New campaign fields get correct defaults when not explicitly set."""
        from app.core.database import async_session
        from app.models.campaign import Campaign
        from app.models.company import Company

        async with async_session() as session:
            company = Company(
                name="Default Co", email="default@co.com",
                password_hash="hash", balance=1000,
            )
            session.add(company)
            await session.flush()

            campaign = Campaign(
                company_id=company.id, title="Default Test",
                brief="Brief", budget_total=100, budget_remaining=100,
                payout_rules={},
                start_date=datetime.now(timezone.utc),
                end_date=datetime.now(timezone.utc),
            )
            session.add(campaign)
            await session.commit()

            from sqlalchemy import select
            result = await session.execute(
                select(Campaign).where(Campaign.id == campaign.id)
            )
            c = result.scalar_one()
            assert c.ai_generated_brief is False
            assert c.budget_exhaustion_action == "auto_pause"
            assert c.invitation_count == 0
            assert c.accepted_count == 0
            assert c.rejected_count == 0
            assert c.expired_count == 0

    async def test_user_new_fields_persist(self, _async_db):
        from app.core.database import async_session
        from app.models.user import User

        async with async_session() as session:
            user = User(
                email="scraped@test.com", password_hash="hash",
                scraped_profiles={"x": {"follower_count": 1500}},
                ai_detected_niches=["finance", "tech"],
            )
            session.add(user)
            await session.commit()

            from sqlalchemy import select
            result = await session.execute(
                select(User).where(User.email == "scraped@test.com")
            )
            u = result.scalar_one()
            assert u.scraped_profiles == {"x": {"follower_count": 1500}}
            assert u.ai_detected_niches == ["finance", "tech"]
            assert u.last_scraped_at is None

    async def test_user_defaults_persist(self, _async_db):
        """New user fields get correct defaults when not explicitly set."""
        from app.core.database import async_session
        from app.models.user import User

        async with async_session() as session:
            user = User(email="defaults@test.com", password_hash="hash")
            session.add(user)
            await session.commit()

            from sqlalchemy import select
            result = await session.execute(
                select(User).where(User.email == "defaults@test.com")
            )
            u = result.scalar_one()
            # JSON defaults are set at insert time
            assert u.scraped_profiles == {} or u.scraped_profiles is None
            assert u.ai_detected_niches == [] or u.ai_detected_niches is None
            assert u.last_scraped_at is None

    async def test_assignment_invitation_fields_persist(self, _async_db):
        from app.core.database import async_session
        from app.models.assignment import CampaignAssignment
        from app.models.user import User
        from app.models.campaign import Campaign
        from app.models.company import Company

        async with async_session() as session:
            company = Company(
                name="Assign Co", email="assign@co.com",
                password_hash="hash", balance=1000,
            )
            session.add(company)
            await session.flush()

            campaign = Campaign(
                company_id=company.id, title="Assignment Test",
                brief="Brief", budget_total=500, budget_remaining=500,
                payout_rules={},
                start_date=datetime.now(timezone.utc),
                end_date=datetime.now(timezone.utc),
            )
            session.add(campaign)
            await session.flush()

            user = User(email="assign@test.com", password_hash="hash")
            session.add(user)
            await session.flush()

            now = datetime.now(timezone.utc)
            assignment = CampaignAssignment(
                campaign_id=campaign.id,
                user_id=user.id,
                status="pending_invitation",
                expires_at=now + timedelta(days=3),
            )
            session.add(assignment)
            await session.commit()

            from sqlalchemy import select
            result = await session.execute(
                select(CampaignAssignment).where(
                    CampaignAssignment.user_id == user.id
                )
            )
            a = result.scalar_one()
            assert a.status == "pending_invitation"
            assert a.expires_at is not None
            assert a.responded_at is None

    async def test_assignment_default_status_is_pending_invitation(self, _async_db):
        """Assignment created without explicit status gets pending_invitation."""
        from app.core.database import async_session
        from app.models.assignment import CampaignAssignment
        from app.models.user import User
        from app.models.campaign import Campaign
        from app.models.company import Company

        async with async_session() as session:
            company = Company(
                name="Default Status Co", email="defstatus@co.com",
                password_hash="hash", balance=1000,
            )
            session.add(company)
            await session.flush()

            campaign = Campaign(
                company_id=company.id, title="Default Status Test",
                brief="Brief", budget_total=500, budget_remaining=500,
                payout_rules={},
                start_date=datetime.now(timezone.utc),
                end_date=datetime.now(timezone.utc),
            )
            session.add(campaign)
            await session.flush()

            user = User(email="defstatus@test.com", password_hash="hash")
            session.add(user)
            await session.flush()

            assignment = CampaignAssignment(
                campaign_id=campaign.id,
                user_id=user.id,
            )
            session.add(assignment)
            await session.commit()

            from sqlalchemy import select
            result = await session.execute(
                select(CampaignAssignment).where(
                    CampaignAssignment.user_id == user.id
                )
            )
            a = result.scalar_one()
            assert a.status == "pending_invitation"
            assert float(a.payout_multiplier) == 1.0
