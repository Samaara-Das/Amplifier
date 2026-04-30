"""add_drafts_commands_status

Revision ID: 63d9159c4ce6
Revises: a1b2c3d4e5f6
Create Date: 2026-05-01 00:03:05.945332

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '63d9159c4ce6'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'drafts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('campaign_id', sa.Integer(), nullable=False),
        sa.Column('platform', sa.String(length=20), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('image_url', sa.String(length=500), nullable=True),
        sa.Column('image_local_path', sa.String(length=500), nullable=True),
        sa.Column('quality_score', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('iteration', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('local_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_drafts_campaign_id', 'drafts', ['campaign_id'])
    op.create_index('ix_drafts_local_id', 'drafts', ['local_id'])
    op.create_index('ix_drafts_status', 'drafts', ['status'])
    op.create_index('ix_drafts_user_id', 'drafts', ['user_id'])

    op.create_table(
        'agent_commands',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('type', sa.String(length=40), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_agent_commands_status', 'agent_commands', ['status'])
    op.create_index('ix_agent_commands_type', 'agent_commands', ['type'])
    op.create_index('ix_agent_commands_user_id', 'agent_commands', ['user_id'])

    op.create_table(
        'agent_status',
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('running', sa.Boolean(), nullable=False),
        sa.Column('paused', sa.Boolean(), nullable=False),
        sa.Column('last_seen', sa.DateTime(timezone=True), nullable=True),
        sa.Column('platform_health', sa.JSON(), nullable=False),
        sa.Column('ai_keys_configured', sa.JSON(), nullable=False),
        sa.Column('version', sa.String(length=20), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('user_id'),
    )


def downgrade() -> None:
    op.drop_table('agent_status')
    op.drop_index('ix_agent_commands_user_id', table_name='agent_commands')
    op.drop_index('ix_agent_commands_type', table_name='agent_commands')
    op.drop_index('ix_agent_commands_status', table_name='agent_commands')
    op.drop_table('agent_commands')
    op.drop_index('ix_drafts_user_id', table_name='drafts')
    op.drop_index('ix_drafts_status', table_name='drafts')
    op.drop_index('ix_drafts_local_id', table_name='drafts')
    op.drop_index('ix_drafts_campaign_id', table_name='drafts')
    op.drop_table('drafts')
