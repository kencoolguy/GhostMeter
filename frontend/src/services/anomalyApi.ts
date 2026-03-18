import { api } from "./api";
import type {
  AnomalyActiveResponse,
  AnomalyInjectRequest,
  AnomalyScheduleBatchSet,
  AnomalyScheduleResponse,
  ApiResponse,
} from "../types";

export const anomalyApi = {
  inject: (deviceId: string, data: AnomalyInjectRequest) =>
    api
      .post<ApiResponse<AnomalyActiveResponse>>(
        `/devices/${deviceId}/anomaly`,
        data
      )
      .then((r) => r.data),

  getActive: (deviceId: string) =>
    api
      .get<ApiResponse<AnomalyActiveResponse[]>>(
        `/devices/${deviceId}/anomaly`
      )
      .then((r) => r.data),

  remove: (deviceId: string, registerName: string) =>
    api
      .delete<ApiResponse<null>>(
        `/devices/${deviceId}/anomaly/${registerName}`
      )
      .then((r) => r.data),

  clearAll: (deviceId: string) =>
    api
      .delete<ApiResponse<null>>(`/devices/${deviceId}/anomaly`)
      .then((r) => r.data),

  getSchedules: (deviceId: string) =>
    api
      .get<ApiResponse<AnomalyScheduleResponse[]>>(
        `/devices/${deviceId}/anomaly/schedules`
      )
      .then((r) => r.data),

  setSchedules: (deviceId: string, data: AnomalyScheduleBatchSet) =>
    api
      .put<ApiResponse<AnomalyScheduleResponse[]>>(
        `/devices/${deviceId}/anomaly/schedules`,
        data
      )
      .then((r) => r.data),

  deleteSchedules: (deviceId: string) =>
    api
      .delete<ApiResponse<null>>(
        `/devices/${deviceId}/anomaly/schedules`
      )
      .then((r) => r.data),
};
