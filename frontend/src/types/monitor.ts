// --- Monitor Dashboard Types ---

export interface RegisterData {
  name: string;
  value: number;
  unit: string;
}

export interface CommunicationStats {
  request_count: number;
  success_count: number;
  error_count: number;
  avg_response_ms: number;
}

export interface MqttStats {
  request_count: number;
  success_count: number;
  error_count: number;
}

export interface FaultInfo {
  fault_type: string;
  params: Record<string, unknown>;
}

export interface DeviceMonitorData {
  device_id: string;
  name: string;
  slave_id: number;
  port: number;
  status: string;
  registers: RegisterData[];
  active_anomalies: string[];
  active_fault: FaultInfo | null;
  stats: CommunicationStats;
  mqtt_stats: MqttStats | null;
}

export interface MonitorEvent {
  timestamp: string;
  device_id: string;
  device_name: string;
  event_type: string;
  detail: string;
}

export interface MonitorUpdate {
  type: "monitor_update";
  timestamp: string;
  devices: DeviceMonitorData[];
  events: MonitorEvent[];
  mqtt_broker_connected: boolean;
}

export interface RegisterHistoryPoint {
  timestamp: number; // Date.now() ms
  value: number;
}
