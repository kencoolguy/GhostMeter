export interface MqttBrokerSettings {
  host: string;
  port: number;
  username: string;
  password: string;
  client_id: string;
  use_tls: boolean;
}

export interface MqttPublishConfig {
  device_id: string;
  topic_template: string;
  payload_mode: "batch" | "per_register";
  publish_interval_seconds: number;
  qos: number;
  retain: boolean;
  enabled: boolean;
}

export interface MqttPublishConfigWrite {
  topic_template: string;
  payload_mode: "batch" | "per_register";
  publish_interval_seconds: number;
  qos: number;
  retain: boolean;
}

export interface MqttTestResult {
  success: boolean;
  message: string;
}
