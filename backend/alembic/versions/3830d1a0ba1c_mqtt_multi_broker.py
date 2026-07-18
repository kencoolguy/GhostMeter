"""mqtt multi broker

Revision ID: 3830d1a0ba1c
Revises: a7c3e91f4b20
Create Date: 2026-07-18 15:40:02.284359

Turns the single-row mqtt_broker_settings into a named multi-row table and
re-keys mqtt_publish_configs from one-per-device to one-per-(device, broker).
Existing data is preserved: the current broker row becomes "default" and all
existing publish configs are attached to it.
"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3830d1a0ba1c'
down_revision: Union[str, None] = 'a7c3e91f4b20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # --- mqtt_broker_settings: add unique, not-null name ---
    op.add_column(
        "mqtt_broker_settings", sa.Column("name", sa.String(length=100), nullable=True)
    )
    conn.execute(
        sa.text("UPDATE mqtt_broker_settings SET name = 'default' WHERE name IS NULL")
    )

    # Orphan guard: publish configs existing with no broker row to attach to.
    has_configs = conn.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM mqtt_publish_configs)")
    ).scalar()
    has_broker = conn.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM mqtt_broker_settings)")
    ).scalar()
    if has_configs and not has_broker:
        conn.execute(
            sa.text(
                "INSERT INTO mqtt_broker_settings "
                "(id, name, host, port, username, password, client_id, use_tls) "
                "VALUES (:id, 'default', 'localhost', 1883, '', '', 'ghostmeter', false)"
            ),
            {"id": str(uuid.uuid4())},
        )

    op.alter_column("mqtt_broker_settings", "name", nullable=False)
    op.create_unique_constraint(
        "uq_mqtt_broker_settings_name", "mqtt_broker_settings", ["name"]
    )

    # --- mqtt_publish_configs: device_id unique -> (device_id, broker_id) ---
    op.add_column(
        "mqtt_publish_configs", sa.Column("broker_id", sa.Uuid(), nullable=True)
    )
    conn.execute(
        sa.text(
            "UPDATE mqtt_publish_configs "
            "SET broker_id = (SELECT id FROM mqtt_broker_settings ORDER BY name LIMIT 1)"
        )
    )
    op.alter_column("mqtt_publish_configs", "broker_id", nullable=False)
    op.create_foreign_key(
        "mqtt_publish_configs_broker_id_fkey",
        "mqtt_publish_configs",
        "mqtt_broker_settings",
        ["broker_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_constraint(
        "mqtt_publish_configs_device_id_key", "mqtt_publish_configs", type_="unique"
    )
    op.create_unique_constraint(
        "uq_mqtt_publish_device_broker",
        "mqtt_publish_configs",
        ["device_id", "broker_id"],
    )


def downgrade() -> None:
    conn = op.get_bind()

    # Keep only one config per device (the first by id) before restoring uniqueness.
    conn.execute(
        sa.text(
            "DELETE FROM mqtt_publish_configs WHERE id NOT IN ("
            "SELECT DISTINCT ON (device_id) id FROM mqtt_publish_configs "
            "ORDER BY device_id, id)"
        )
    )
    op.drop_constraint(
        "uq_mqtt_publish_device_broker", "mqtt_publish_configs", type_="unique"
    )
    op.drop_constraint(
        "mqtt_publish_configs_broker_id_fkey", "mqtt_publish_configs", type_="foreignkey"
    )
    op.drop_column("mqtt_publish_configs", "broker_id")
    op.create_unique_constraint(
        "mqtt_publish_configs_device_id_key", "mqtt_publish_configs", ["device_id"]
    )

    # Keep only one broker row (single-row semantics) before dropping name.
    conn.execute(
        sa.text(
            "DELETE FROM mqtt_broker_settings WHERE id NOT IN ("
            "SELECT id FROM mqtt_broker_settings ORDER BY name LIMIT 1)"
        )
    )
    op.drop_constraint(
        "uq_mqtt_broker_settings_name", "mqtt_broker_settings", type_="unique"
    )
    op.drop_column("mqtt_broker_settings", "name")
