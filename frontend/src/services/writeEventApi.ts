import { api } from "./api";
import type { ApiResponse, WriteEventSummary } from "../types";

export const writeEventApi = {
  list: (deviceId: string) =>
    api
      .get<ApiResponse<WriteEventSummary[]>>(`/devices/${deviceId}/write-events`)
      .then((r) => r.data),

  ack: (deviceId: string) =>
    api
      .post<ApiResponse<{ unread: number }>>(
        `/devices/${deviceId}/write-events/ack`,
      )
      .then((r) => r.data),
};
