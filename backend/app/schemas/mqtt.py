"""Pydantic schemas for MQTT configuration."""

from pydantic import BaseModel, field_validator


class MqttBrokerSettingsRead(BaseModel):
    """Broker settings response (password masked)."""

    host: str = "localhost"
    port: int = 1883
    username: str = ""
    password: str = ""
    client_id: str = "ghostmeter"
    use_tls: bool = False


class MqttBrokerSettingsWrite(BaseModel):
    """Broker settings update request."""

    host: str = "localhost"
    port: int = 1883
    username: str = ""
    password: str = ""
    client_id: str = "ghostmeter"
    use_tls: bool = False

    @field_validator("port")
    @classmethod
    def validate_port(cls, v: int) -> int:
        if not 1 <= v <= 65535:
            raise ValueError("Port must be between 1 and 65535")
        return v


class MqttPublishConfigRead(BaseModel):
    """Per-device MQTT publish config response."""

    device_id: str
    topic_template: str
    payload_mode: str
    publish_interval_seconds: int
    qos: int
    retain: bool
    enabled: bool


class MqttPublishConfigWrite(BaseModel):
    """Per-device MQTT publish config create/update."""

    topic_template: str = "telemetry/{device_name}"
    payload_mode: str = "batch"
    publish_interval_seconds: int = 5
    qos: int = 0
    retain: bool = False

    @field_validator("payload_mode")
    @classmethod
    def validate_payload_mode(cls, v: str) -> str:
        if v not in ("batch", "per_register"):
            raise ValueError("payload_mode must be 'batch' or 'per_register'")
        return v

    @field_validator("qos")
    @classmethod
    def validate_qos(cls, v: int) -> int:
        if v not in (0, 1, 2):
            raise ValueError("QoS must be 0, 1, or 2")
        return v

    @field_validator("publish_interval_seconds")
    @classmethod
    def validate_interval(cls, v: int) -> int:
        if v < 1:
            raise ValueError("Interval must be at least 1 second")
        return v


class MqttTestResult(BaseModel):
    """Result of broker connection test."""

    success: bool
    message: str
