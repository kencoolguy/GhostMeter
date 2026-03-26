"""merge heads

Revision ID: b241433f7174
Revises: 6e6c8a4265de, 884c7934de25
Create Date: 2026-03-26 18:21:12.815683

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b241433f7174'
down_revision: Union[str, None] = ('6e6c8a4265de', '884c7934de25')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
