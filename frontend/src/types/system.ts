export interface ImportResult {
  templates_created: number;
  templates_updated: number;
  templates_skipped: number;
  devices_created: number;
  devices_updated: number;
  simulation_configs_set: number;
  anomaly_schedules_set: number;
}

export interface SystemExport {
  version: string;
  exported_at: string;
  templates: unknown[];
  devices: unknown[];
  simulation_configs: unknown[];
  anomaly_schedules: unknown[];
}
