import { api } from "./api";
import type {
  ApiResponse,
  CreateProfile,
  SimulationProfile,
  UpdateProfile,
} from "../types";

export const profileApi = {
  list: (templateId: string) =>
    api
      .get<ApiResponse<SimulationProfile[]>>("/simulation-profiles", {
        params: { template_id: templateId },
      })
      .then((r) => r.data),

  get: (id: string) =>
    api
      .get<ApiResponse<SimulationProfile>>(`/simulation-profiles/${id}`)
      .then((r) => r.data),

  create: (data: CreateProfile) =>
    api
      .post<ApiResponse<SimulationProfile>>("/simulation-profiles", data)
      .then((r) => r.data),

  update: (id: string, data: UpdateProfile) =>
    api
      .put<ApiResponse<SimulationProfile>>(`/simulation-profiles/${id}`, data)
      .then((r) => r.data),

  delete: (id: string) =>
    api
      .delete<ApiResponse<null>>(`/simulation-profiles/${id}`)
      .then((r) => r.data),
};
