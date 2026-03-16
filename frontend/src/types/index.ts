export interface HealthResponse {
  status: "ok" | "error";
  database: "connected" | "disconnected";
  version: string;
}

export interface ApiErrorResponse {
  detail: string;
  error_code: string;
}
