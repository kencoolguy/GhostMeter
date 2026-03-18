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


class SimulationConfig(Base):
    """Per-register simulation configuration for a device instance."""

    __tablename__ = "simulation_configs"
    __table_args__ = (
        UniqueConstraint(
            "device_id", "register_name",
            name="uq_sim_config_device_register",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    device_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("device_instances.id", ondelete="CASCADE"), nullable=False
    )
    register_name: Mapped[str] = mapped_column(String(100), nullable=False)
    data_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    mode_params: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    update_interval_ms: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1000
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
