export interface HealthResponse {
  status: "ok" | "error";
  database: "connected" | "disconnected";
  version: string;
}

export interface ApiErrorResponse {
  detail: string;
  error_code: string;
}

export type {
  BatchCreateDevice,
  CreateDevice,
  DeviceDetail,
  DeviceSummary,
  RegisterValue,
  UpdateDevice,
} from "./device";

export type {
  ApiResponse,
  CreateTemplate,
  RegisterDefinition,
  TemplateClone,
  TemplateDetail,
  TemplateSummary,
  UpdateTemplate,
} from "./template";
