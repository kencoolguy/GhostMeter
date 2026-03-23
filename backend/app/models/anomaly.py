"""ORM model for anomaly injection schedules."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base


class AnomalySchedule(Base):
    """Scheduled anomaly injection for a device register."""

    __tablename__ = "anomaly_schedules"
    __table_args__ = (
        UniqueConstraint(
            "device_id", "register_name", "trigger_after_seconds",
            name="uq_anomaly_schedule_device_register_trigger",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    device_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("device_instances.id", ondelete="CASCADE"), nullable=False
    )
    register_name: Mapped[str] = mapped_column(String(100), nullable=False)
    anomaly_type: Mapped[str] = mapped_column(String(20), nullable=False)
    anomaly_params: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    trigger_after_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False
    )
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
