import { api } from "./api";
import type { ApiResponse } from "../types";
import type {
  MqttBroker,
  MqttBrokerWrite,
  MqttPublishConfig,
  MqttPublishConfigWrite,
  MqttTestResult,
} from "../types/mqtt";

export const mqttApi = {
  listBrokers: () =>
    api.get<ApiResponse<MqttBroker[]>>("/system/mqtt/brokers").then((r) => r.data),

  createBroker: (data: MqttBrokerWrite) =>
    api.post<ApiResponse<MqttBroker>>("/system/mqtt/brokers", data).then((r) => r.data),

  updateBroker: (brokerId: string, data: MqttBrokerWrite) =>
    api
      .put<ApiResponse<MqttBroker>>(`/system/mqtt/brokers/${brokerId}`, data)
      .then((r) => r.data),

  deleteBroker: (brokerId: string) =>
    api.delete<ApiResponse<null>>(`/system/mqtt/brokers/${brokerId}`).then((r) => r.data),

  testConnection: (data: MqttBrokerWrite) =>
    api.post<ApiResponse<MqttTestResult>>("/system/mqtt/test", data).then((r) => r.data),

  getDeviceConfigs: (deviceId: string) =>
    api
      .get<ApiResponse<MqttPublishConfig[]>>(`/system/devices/${deviceId}/mqtt`)
      .then((r) => r.data),

  updateDeviceConfig: (deviceId: string, brokerId: string, data: MqttPublishConfigWrite) =>
    api
      .put<ApiResponse<MqttPublishConfig>>(
        `/system/devices/${deviceId}/mqtt/${brokerId}`,
        data,
      )
      .then((r) => r.data),

  deleteDeviceConfig: (deviceId: string, brokerId: string) =>
    api
      .delete<ApiResponse<null>>(`/system/devices/${deviceId}/mqtt/${brokerId}`)
      .then((r) => r.data),

  startPublishing: (deviceId: string, brokerId?: string) =>
    api
      .post<ApiResponse<MqttPublishConfig[]>>(
        `/system/devices/${deviceId}/mqtt/start`,
        undefined,
        brokerId ? { params: { broker_id: brokerId } } : undefined,
      )
      .then((r) => r.data),

  stopPublishing: (deviceId: string, brokerId?: string) =>
    api
      .post<ApiResponse<MqttPublishConfig[]>>(
        `/system/devices/${deviceId}/mqtt/stop`,
        undefined,
        brokerId ? { params: { broker_id: brokerId } } : undefined,
      )
      .then((r) => r.data),
};
