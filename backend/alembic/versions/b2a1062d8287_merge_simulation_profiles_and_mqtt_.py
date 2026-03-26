"""merge simulation_profiles and mqtt migrations

Revision ID: b2a1062d8287
Revises: 8c0da865d279, eda1e6420ebd
Create Date: 2026-03-25 08:55:52.557229

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2a1062d8287'
down_revision: Union[str, None] = ('8c0da865d279', 'eda1e6420ebd')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
