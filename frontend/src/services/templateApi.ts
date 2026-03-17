import { api } from "./api";
import type {
  ApiResponse,
  CreateTemplate,
  TemplateClone,
  TemplateDetail,
  TemplateSummary,
  UpdateTemplate,
} from "../types";

export const templateApi = {
  list: () =>
    api.get<ApiResponse<TemplateSummary[]>>("/templates").then((r) => r.data),

  get: (id: string) =>
    api.get<ApiResponse<TemplateDetail>>(`/templates/${id}`).then((r) => r.data),

  create: (data: CreateTemplate) =>
    api
      .post<ApiResponse<TemplateDetail>>("/templates", data)
      .then((r) => r.data),

  update: (id: string, data: UpdateTemplate) =>
    api
      .put<ApiResponse<TemplateDetail>>(`/templates/${id}`, data)
      .then((r) => r.data),

  delete: (id: string) =>
    api.delete<ApiResponse<null>>(`/templates/${id}`).then((r) => r.data),

  clone: (id: string, data?: TemplateClone) =>
    api
      .post<ApiResponse<TemplateDetail>>(`/templates/${id}/clone`, data)
      .then((r) => r.data),

  exportTemplate: (id: string) =>
    api
      .get(`/templates/${id}/export`, { responseType: "blob" })
      .then((r) => r.data),

  importTemplate: (file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    return api
      .post<ApiResponse<TemplateDetail>>("/templates/import", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      })
      .then((r) => r.data);
  },
};
