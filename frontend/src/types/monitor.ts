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
}

export interface RegisterHistoryPoint {
  timestamp: number; // Date.now() ms
  value: number;
}
