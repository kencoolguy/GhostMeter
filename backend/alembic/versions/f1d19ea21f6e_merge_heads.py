"""merge heads

Revision ID: f1d19ea21f6e
Revises: 8c0da865d279, eda1e6420ebd
Create Date: 2026-03-26 18:15:21.500381

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1d19ea21f6e'
down_revision: Union[str, None] = ('8c0da865d279', 'eda1e6420ebd')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
