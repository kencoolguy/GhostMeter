// --- Simulation Config ---

export interface SimulationConfigRequest {
  register_name: string;
  data_mode: "static" | "random" | "daily_curve" | "computed" | "accumulator";
  mode_params: Record<string, unknown>;
  is_enabled: boolean;
  update_interval_ms: number;
}

export interface SimulationConfigResponse extends SimulationConfigRequest {
  id: string;
  device_id: string;
  created_at: string;
  updated_at: string;
}

export interface SimulationConfigBatchSet {
  configs: SimulationConfigRequest[];
}

// --- Anomaly ---

export type AnomalyType = "spike" | "drift" | "flatline" | "out_of_range" | "data_loss";

export interface AnomalyInjectRequest {
  register_name: string;
  anomaly_type: AnomalyType;
  anomaly_params: Record<string, unknown>;
}

export interface AnomalyActiveResponse {
  register_name: string;
  anomaly_type: AnomalyType;
  anomaly_params: Record<string, unknown>;
}

export interface AnomalyScheduleRequest {
  register_name: string;
  anomaly_type: AnomalyType;
  anomaly_params: Record<string, unknown>;
  trigger_after_seconds: number;
  duration_seconds: number;
  is_enabled: boolean;
}

export interface AnomalyScheduleResponse extends AnomalyScheduleRequest {
  id: string;
  device_id: string;
  created_at: string;
  updated_at: string;
}

export interface AnomalyScheduleBatchSet {
  schedules: AnomalyScheduleRequest[];
}

// --- Fault ---

export type FaultType = "delay" | "timeout" | "exception" | "intermittent";

export interface FaultConfigRequest {
  fault_type: FaultType;
  params: Record<string, unknown>;
}

export interface FaultConfigResponse {
  fault_type: FaultType;
  params: Record<string, unknown>;
}
