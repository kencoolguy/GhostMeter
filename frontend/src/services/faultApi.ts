import { api } from "./api";
import type {
  ApiResponse,
  FaultConfigRequest,
  FaultConfigResponse,
} from "../types";

export const faultApi = {
  get: (deviceId: string) =>
    api
      .get<ApiResponse<FaultConfigResponse | null>>(
        `/devices/${deviceId}/fault`
      )
      .then((r) => r.data),

  set: (deviceId: string, data: FaultConfigRequest) =>
    api
      .put<ApiResponse<FaultConfigResponse>>(
        `/devices/${deviceId}/fault`,
        data
      )
      .then((r) => r.data),

  clear: (deviceId: string) =>
    api
      .delete<ApiResponse<null>>(`/devices/${deviceId}/fault`)
      .then((r) => r.data),
};
