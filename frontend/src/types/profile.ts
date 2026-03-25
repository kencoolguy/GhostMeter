export type DataMode = "static" | "random" | "daily_curve" | "computed" | "accumulator";

export interface ProfileConfigEntry {
  register_name: string;
  data_mode: DataMode;
  mode_params: Record<string, unknown>;
  is_enabled: boolean;
  update_interval_ms: number;
}

export interface SimulationProfile {
  id: string;
  template_id: string;
  name: string;
  description: string | null;
  is_builtin: boolean;
  is_default: boolean;
  configs: ProfileConfigEntry[];
  created_at: string;
  updated_at: string;
}

export interface CreateProfile {
  template_id: string;
  name: string;
  description?: string | null;
  is_default?: boolean;
  configs: ProfileConfigEntry[];
}

export interface UpdateProfile {
  name?: string;
  description?: string | null;
  is_default?: boolean;
  configs?: ProfileConfigEntry[];
}
