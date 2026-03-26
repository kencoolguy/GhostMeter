import { api } from "./api";
import type {
  ApiResponse,
  BatchActionResult,
  BatchCreateDevice,
  CreateDevice,
  DeviceDetail,
  DeviceSummary,
  RegisterValue,
  UpdateDevice,
} from "../types";

export const deviceApi = {
  list: () =>
    api.get<ApiResponse<DeviceSummary[]>>("/devices").then((r) => r.data),

  get: (id: string) =>
    api.get<ApiResponse<DeviceDetail>>(`/devices/${id}`).then((r) => r.data),

  create: (data: CreateDevice) =>
    api.post<ApiResponse<DeviceSummary>>("/devices", data).then((r) => r.data),

  batchCreate: (data: BatchCreateDevice) =>
    api
      .post<ApiResponse<DeviceSummary[]>>("/devices/batch", data)
      .then((r) => r.data),

  update: (id: string, data: UpdateDevice) =>
    api
      .put<ApiResponse<DeviceSummary>>(`/devices/${id}`, data)
      .then((r) => r.data),

  delete: (id: string) =>
    api.delete<ApiResponse<null>>(`/devices/${id}`).then((r) => r.data),

  start: (id: string) =>
    api
      .post<ApiResponse<DeviceSummary>>(`/devices/${id}/start`)
      .then((r) => r.data),

  stop: (id: string) =>
    api
      .post<ApiResponse<DeviceSummary>>(`/devices/${id}/stop`)
      .then((r) => r.data),

  getRegisters: (id: string) =>
    api
      .get<ApiResponse<RegisterValue[]>>(`/devices/${id}/registers`)
      .then((r) => r.data),

  batchStart: (deviceIds: string[]) =>
    api
      .post<ApiResponse<BatchActionResult>>("/devices/batch/start", {
        device_ids: deviceIds,
      })
      .then((r) => r.data),

  batchStop: (deviceIds: string[]) =>
    api
      .post<ApiResponse<BatchActionResult>>("/devices/batch/stop", {
        device_ids: deviceIds,
      })
      .then((r) => r.data),

  batchDelete: (deviceIds: string[]) =>
    api
      .post<ApiResponse<BatchActionResult>>("/devices/batch/delete", {
        device_ids: deviceIds,
      })
      .then((r) => r.data),
};
