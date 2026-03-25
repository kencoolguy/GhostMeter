"""MQTT-related ORM models."""

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MqttBrokerSettings(Base):
    """Global MQTT broker connection settings (single row)."""

    __tablename__ = "mqtt_broker_settings"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    host: Mapped[str] = mapped_column(String(255), default="localhost")
    port: Mapped[int] = mapped_column(Integer, default=1883)
    username: Mapped[str] = mapped_column(String(255), default="")
    password: Mapped[str] = mapped_column(String(255), default="")
    client_id: Mapped[str] = mapped_column(String(255), default="ghostmeter")
    use_tls: Mapped[bool] = mapped_column(Boolean, default=False)


class MqttPublishConfig(Base):
    """Per-device MQTT publish configuration."""

    __tablename__ = "mqtt_publish_configs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    device_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("device_instances.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    topic_template: Mapped[str] = mapped_column(
        String(500), default="telemetry/{device_name}"
    )
    payload_mode: Mapped[str] = mapped_column(String(20), default="batch")
    publish_interval_seconds: Mapped[int] = mapped_column(Integer, default=5)
    qos: Mapped[int] = mapped_column(Integer, default=0)
    retain: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
