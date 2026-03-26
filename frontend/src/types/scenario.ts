export interface ScenarioStepCreate {
  register_name: string;
  anomaly_type: string;
  anomaly_params: Record<string, number | string | boolean>;
  trigger_at_seconds: number;
  duration_seconds: number;
  sort_order: number;
}

export interface ScenarioStepResponse extends ScenarioStepCreate {
  id: string;
}

export interface ScenarioSummary {
  id: string;
  template_id: string;
  template_name: string;
  name: string;
  description: string | null;
  is_builtin: boolean;
  total_duration_seconds: number;
  created_at: string;
  updated_at: string;
}

export interface ScenarioDetail extends ScenarioSummary {
  steps: ScenarioStepResponse[];
}

export interface ScenarioCreate {
  template_id: string;
  name: string;
  description?: string | null;
  steps: ScenarioStepCreate[];
}

export interface ScenarioUpdate {
  name: string;
  description?: string | null;
  steps: ScenarioStepCreate[];
}

export interface ScenarioExport {
  name: string;
  description: string | null;
  template_name: string;
  steps: ScenarioStepCreate[];
}

export interface ActiveStepStatus {
  register_name: string;
  anomaly_type: string;
  remaining_seconds: number;
}

export interface ScenarioExecutionStatus {
  scenario_id: string;
  scenario_name: string;
  status: "running" | "completed";
  elapsed_seconds: number;
  total_duration_seconds: number;
  active_steps: ActiveStepStatus[];
}
