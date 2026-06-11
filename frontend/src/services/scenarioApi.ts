import { api } from "./api";
import type { ApiResponse } from "../types";
import type {
  ScenarioCreate,
  ScenarioDetail,
  ScenarioExecutionStatus,
  ScenarioExport,
  ScenarioSummary,
  ScenarioUpdate,
} from "../types/scenario";

export const scenarioApi = {
  list: (templateId?: string) =>
    api
      .get<ApiResponse<ScenarioSummary[]>>("/scenarios", {
        params: templateId ? { template_id: templateId } : undefined,
      })
      .then((r) => r.data),

  get: (id: string) =>
    api
      .get<ApiResponse<ScenarioDetail>>(`/scenarios/${id}`)
      .then((r) => r.data),

  create: (data: ScenarioCreate) =>
    api
      .post<ApiResponse<ScenarioDetail>>("/scenarios", data)
      .then((r) => r.data),

  update: (id: string, data: ScenarioUpdate) =>
    api
      .put<ApiResponse<ScenarioDetail>>(`/scenarios/${id}`, data)
      .then((r) => r.data),

  delete: (id: string) =>
    api.delete<ApiResponse<null>>(`/scenarios/${id}`).then((r) => r.data),

  export: (id: string) =>
    api
      .post<ApiResponse<ScenarioExport>>(`/scenarios/${id}/export`)
      .then((r) => r.data),

  import: (data: ScenarioExport) =>
    api
      .post<ApiResponse<ScenarioDetail>>("/scenarios/import", data)
      .then((r) => r.data),

  startExecution: (deviceId: string, scenarioId: string) =>
    api
      .post<ApiResponse<null>>(
        `/devices/${deviceId}/scenario/${scenarioId}/start`,
      )
      .then((r) => r.data),

  stopExecution: (deviceId: string) =>
    api
      .post<ApiResponse<null>>(`/devices/${deviceId}/scenario/stop`)
      .then((r) => r.data),

  getExecutionStatus: (deviceId: string) =>
    api
      .get<ApiResponse<ScenarioExecutionStatus>>(
        `/devices/${deviceId}/scenario/status`,
      )
      .then((r) => r.data),
};
