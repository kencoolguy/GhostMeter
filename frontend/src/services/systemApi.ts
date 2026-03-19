import { api } from "./api";
import type { ApiResponse } from "../types";
import type { ImportResult } from "../types/system";

export const systemApi = {
  exportConfig: () =>
    api.get<Record<string, unknown>>("/system/export").then((r) => r.data),

  importConfig: (data: Record<string, unknown>) =>
    api.post<ApiResponse<ImportResult>>("/system/import", data).then((r) => r.data),
};
