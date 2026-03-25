export interface DeviceSummary {
  id: string;
  template_id: string;
  template_name: string;
  name: string;
  slave_id: number;
  status: "stopped" | "running" | "error";
  port: number;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface RegisterValue {
  name: string;
  address: number;
  function_code: number;
  data_type: string;
  byte_order: string;
  scale_factor: number;
  unit: string | null;
  description: string | null;
  value: number | null;
}

export interface DeviceDetail extends DeviceSummary {
  registers: RegisterValue[];
}

export interface CreateDevice {
  template_id: string;
  name: string;
  slave_id: number;
  port?: number;
  description?: string | null;
  profile_id?: string | null;
}

export interface BatchCreateDevice {
  template_id: string;
  slave_id_start: number;
  slave_id_end: number;
  port?: number;
  name_prefix?: string | null;
  description?: string | null;
  profile_id?: string | null;
}

export interface BatchActionResult {
  success_count: number;
  skipped_count: number;
  error_count: number;
}

export interface UpdateDevice {
  name: string;
  slave_id: number;
  port?: number;
  description?: string | null;
}
