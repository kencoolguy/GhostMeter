import { api } from "./api";
import type {
  ApiResponse,
  SimulationConfigBatchSet,
  SimulationConfigResponse,
} from "../types";

export const simulationApi = {
  getConfigs: (deviceId: string) =>
    api
      .get<ApiResponse<SimulationConfigResponse[]>>(
        `/devices/${deviceId}/simulation`
      )
      .then((r) => r.data),

  setConfigs: (deviceId: string, data: SimulationConfigBatchSet) =>
    api
      .put<ApiResponse<SimulationConfigResponse[]>>(
        `/devices/${deviceId}/simulation`,
        data
      )
      .then((r) => r.data),

  patchConfig: (
    deviceId: string,
    registerName: string,
    data: SimulationConfigBatchSet["configs"][0]
  ) =>
    api
      .patch<ApiResponse<SimulationConfigResponse>>(
        `/devices/${deviceId}/simulation/${registerName}`,
        data
      )
      .then((r) => r.data),

  deleteConfigs: (deviceId: string) =>
    api
      .delete<ApiResponse<null>>(`/devices/${deviceId}/simulation`)
      .then((r) => r.data),
};
