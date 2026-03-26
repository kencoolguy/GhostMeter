import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base


class DeviceTemplate(Base):
    """Device template defining a register map."""

    __tablename__ = "device_templates"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    protocol: Mapped[str] = mapped_column(
        String(50), nullable=False, default="modbus_tcp"
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_builtin: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
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

    registers: Mapped[list["RegisterDefinition"]] = relationship(
        back_populates="template",
        cascade="all, delete-orphan",
        order_by="RegisterDefinition.sort_order",
    )


class RegisterDefinition(Base):
    """Single register within a device template."""

    __tablename__ = "register_definitions"
    __table_args__ = (
        UniqueConstraint("template_id", "name", name="uq_register_template_name"),
        UniqueConstraint(
            "template_id", "address", "function_code",
            name="uq_register_template_addr_fc",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    template_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("device_templates.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    address: Mapped[int] = mapped_column(Integer, nullable=False)
    function_code: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=3
    )
    data_type: Mapped[str] = mapped_column(String(20), nullable=False)
    byte_order: Mapped[str] = mapped_column(
        String(30), nullable=False, default="big_endian"
    )
    scale_factor: Mapped[float] = mapped_column(
        Float, nullable=False, default=1.0
    )
    unit: Mapped[str | None] = mapped_column(String(20), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    oid: Mapped[str | None] = mapped_column(String(200), nullable=True)

    template: Mapped["DeviceTemplate"] = relationship(
        back_populates="registers"
    )
