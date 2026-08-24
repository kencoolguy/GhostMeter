export interface MqttBroker {
  id: string;
  name: string;
  host: string;
  port: number;
  username: string;
  password: string;
  client_id: string;
  use_tls: boolean;
  connected: boolean;
}

export interface MqttBrokerWrite {
  name: string;
  host: string;
  port: number;
  username: string;
  password: string;
  client_id: string;
  use_tls: boolean;
}

export interface MqttPublishConfig {
  device_id: string;
  broker_id: string;
  broker_name: string;
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
