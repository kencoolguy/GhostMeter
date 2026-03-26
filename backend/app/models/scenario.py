"""ORM models for scenario mode (scenarios and scenario steps)."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base


class Scenario(Base):
    """A reusable anomaly scenario tied to a device template."""

    __tablename__ = "scenarios"
    __table_args__ = (
        UniqueConstraint(
            "template_id", "name",
            name="uq_scenario_template_name",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    template_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("device_templates.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_builtin: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    total_duration_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False
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

    steps: Mapped[list["ScenarioStep"]] = relationship(
        back_populates="scenario",
        cascade="all, delete-orphan",
        order_by="ScenarioStep.sort_order",
    )


class ScenarioStep(Base):
    """A single anomaly injection step within a scenario."""

    __tablename__ = "scenario_steps"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    scenario_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False
    )
    register_name: Mapped[str] = mapped_column(String(100), nullable=False)
    anomaly_type: Mapped[str] = mapped_column(String(50), nullable=False)
    anomaly_params: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    trigger_at_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False
    )
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )

    scenario: Mapped["Scenario"] = relationship(
        back_populates="steps",
    )
