import { api } from "./api";
import type { ApiResponse } from "../types";
import type {
  MqttBrokerSettings,
  MqttPublishConfig,
  MqttPublishConfigWrite,
  MqttTestResult,
} from "../types/mqtt";

export const mqttApi = {
  getBrokerSettings: () =>
    api.get<ApiResponse<MqttBrokerSettings>>("/system/mqtt").then((r) => r.data),

  updateBrokerSettings: (data: MqttBrokerSettings) =>
    api.put<ApiResponse<MqttBrokerSettings>>("/system/mqtt", data).then((r) => r.data),

  testConnection: (data: MqttBrokerSettings) =>
    api.post<ApiResponse<MqttTestResult>>("/system/mqtt/test", data).then((r) => r.data),

  getDeviceConfig: (deviceId: string) =>
    api
      .get<ApiResponse<MqttPublishConfig | null>>(`/system/devices/${deviceId}/mqtt`)
      .then((r) => r.data),

  updateDeviceConfig: (deviceId: string, data: MqttPublishConfigWrite) =>
    api
      .put<ApiResponse<MqttPublishConfig>>(`/system/devices/${deviceId}/mqtt`, data)
      .then((r) => r.data),

  deleteDeviceConfig: (deviceId: string) =>
    api.delete<ApiResponse<null>>(`/system/devices/${deviceId}/mqtt`).then((r) => r.data),

  startPublishing: (deviceId: string) =>
    api
      .post<ApiResponse<MqttPublishConfig>>(`/system/devices/${deviceId}/mqtt/start`)
      .then((r) => r.data),

  stopPublishing: (deviceId: string) =>
    api
      .post<ApiResponse<MqttPublishConfig>>(`/system/devices/${deviceId}/mqtt/stop`)
      .then((r) => r.data),
};
