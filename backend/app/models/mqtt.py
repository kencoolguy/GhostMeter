"""MQTT-related ORM models."""

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MqttBrokerSettings(Base):
    """A named MQTT broker connection configuration (multi-row)."""

    __tablename__ = "mqtt_broker_settings"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    host: Mapped[str] = mapped_column(String(255), default="localhost")
    port: Mapped[int] = mapped_column(Integer, default=1883)
    username: Mapped[str] = mapped_column(String(255), default="")
    password: Mapped[str] = mapped_column(String(255), default="")
    client_id: Mapped[str] = mapped_column(String(255), default="ghostmeter")
    use_tls: Mapped[bool] = mapped_column(Boolean, default=False)


class MqttPublishConfig(Base):
    """Per-(device, broker) MQTT publish configuration."""

    __tablename__ = "mqtt_publish_configs"
    __table_args__ = (
        UniqueConstraint("device_id", "broker_id", name="uq_mqtt_publish_device_broker"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    device_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("device_instances.id", ondelete="CASCADE"),
        nullable=False,
    )
    broker_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("mqtt_broker_settings.id", ondelete="CASCADE"),
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
