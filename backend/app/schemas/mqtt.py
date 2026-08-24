"""Pydantic schemas for MQTT configuration."""

from pydantic import BaseModel, field_validator


class MqttBrokerWrite(BaseModel):
    """Broker create/update request."""

    name: str
    host: str = "localhost"
    port: int = 1883
    username: str = ""
    password: str = ""
    client_id: str = "ghostmeter"
    use_tls: bool = False

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Broker name must not be empty")
        if len(v) > 100:
            raise ValueError("Broker name must be at most 100 characters")
        return v

    @field_validator("port")
    @classmethod
    def validate_port(cls, v: int) -> int:
        if not 1 <= v <= 65535:
            raise ValueError("Port must be between 1 and 65535")
        return v


class MqttBrokerRead(BaseModel):
    """Broker response (password masked)."""

    id: str
    name: str
    host: str
    port: int
    username: str
    password: str
    client_id: str
    use_tls: bool
    connected: bool = False


class MqttPublishConfigRead(BaseModel):
    """Per-(device, broker) MQTT publish config response."""

    device_id: str
    broker_id: str
    broker_name: str
    topic_template: str
    payload_mode: str
    publish_interval_seconds: int
    qos: int
    retain: bool
    enabled: bool


class MqttPublishConfigWrite(BaseModel):
    """Per-(device, broker) MQTT publish config create/update."""

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
