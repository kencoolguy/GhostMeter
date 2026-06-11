import type { AnomalyType } from "../types";

/**
 * Single source of truth for anomaly-type metadata shared by the
 * Simulation page (AnomalyTab), Scenario editor (StepPopover/TimelineBlock)
 * and ScenarioCard. Param requirements mirror the backend's
 * `app/schemas/anomaly.py` `_REQUIRED_PARAMS`.
 */

export const ANOMALY_TYPE_OPTIONS: { value: AnomalyType; label: string }[] = [
  { value: "spike", label: "Spike" },
  { value: "drift", label: "Drift" },
  { value: "flatline", label: "Flatline" },
  { value: "out_of_range", label: "Out of Range" },
  { value: "data_loss", label: "Data Loss" },
];

export interface AnomalyParamField {
  name: string;
  label: string;
  required: boolean;
  default?: number;
  min?: number;
  max?: number;
  step?: number;
  placeholder?: string;
}

export const ANOMALY_PARAM_FIELDS: Record<AnomalyType, AnomalyParamField[]> = {
  spike: [
    { name: "multiplier", label: "Multiplier", required: true, default: 2.0, min: 0.01, step: 0.5 },
    { name: "probability", label: "Probability", required: true, default: 0.1, min: 0, max: 1, step: 0.1 },
  ],
  drift: [
    { name: "drift_per_second", label: "Drift/sec", required: true, step: 1, placeholder: "e.g. 10" },
    { name: "max_drift", label: "Max drift", required: true, min: 0.01, step: 10, placeholder: "e.g. 500" },
  ],
  flatline: [
    { name: "value", label: "Freeze value", required: false, placeholder: "Empty = freeze current" },
  ],
  out_of_range: [
    { name: "value", label: "Value", required: true, placeholder: "e.g. 99999" },
  ],
  data_loss: [],
};

export const ANOMALY_COLORS: Record<AnomalyType, string> = {
  spike: "#fa8c16",
  drift: "#1890ff",
  flatline: "#8c8c8c",
  out_of_range: "#f5222d",
  data_loss: "#722ed1",
};

export const ANOMALY_FALLBACK_COLOR = "#8c8c8c";
