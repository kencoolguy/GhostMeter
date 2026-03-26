"""add scenarios and scenario_steps tables

Revision ID: 6e6c8a4265de
Revises: f1d19ea21f6e
Create Date: 2026-03-26 18:15:40.180002

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '6e6c8a4265de'
down_revision: Union[str, None] = 'f1d19ea21f6e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'scenarios',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('template_id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_builtin', sa.Boolean(), nullable=False),
        sa.Column('total_duration_seconds', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['template_id'], ['device_templates.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('template_id', 'name', name='uq_scenario_template_name'),
    )
    op.create_table(
        'scenario_steps',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('scenario_id', sa.UUID(), nullable=False),
        sa.Column('register_name', sa.String(length=100), nullable=False),
        sa.Column('anomaly_type', sa.String(length=50), nullable=False),
        sa.Column('anomaly_params', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('trigger_at_seconds', sa.Integer(), nullable=False),
        sa.Column('duration_seconds', sa.Integer(), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['scenario_id'], ['scenarios.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('scenario_steps')
    op.drop_table('scenarios')
