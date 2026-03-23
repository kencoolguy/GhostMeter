import { message } from "antd";
import { create } from "zustand";
import { templateApi } from "../services/templateApi";
import type {
  CreateTemplate,
  TemplateClone,
  TemplateDetail,
  TemplateSummary,
  UpdateTemplate,
} from "../types";

interface TemplateState {
  templates: TemplateSummary[];
  currentTemplate: TemplateDetail | null;
  loading: boolean;
  fetchTemplates: () => Promise<void>;
  fetchTemplate: (id: string) => Promise<void>;
  createTemplate: (data: CreateTemplate) => Promise<TemplateDetail | null>;
  updateTemplate: (
    id: string,
    data: UpdateTemplate
  ) => Promise<TemplateDetail | null>;
  deleteTemplate: (id: string) => Promise<boolean>;
  cloneTemplate: (
    id: string,
    data?: TemplateClone
  ) => Promise<TemplateDetail | null>;
  clearCurrentTemplate: () => void;
}

export const useTemplateStore = create<TemplateState>((set) => ({
  templates: [],
  currentTemplate: null,
  loading: false,

  fetchTemplates: async () => {
    set({ loading: true });
    try {
      const response = await templateApi.list();
      set({ templates: response.data ?? [] });
    } finally {
      set({ loading: false });
    }
  },

  fetchTemplate: async (id: string) => {
    set({ loading: true });
    try {
      const response = await templateApi.get(id);
      set({ currentTemplate: response.data });
    } finally {
      set({ loading: false });
    }
  },

  createTemplate: async (data: CreateTemplate) => {
    set({ loading: true });
    try {
      const response = await templateApi.create(data);
      message.success("Template created successfully");
      return response.data;
    } catch {
      return null;
    } finally {
      set({ loading: false });
    }
  },

  updateTemplate: async (id: string, data: UpdateTemplate) => {
    set({ loading: true });
    try {
      const response = await templateApi.update(id, data);
      message.success("Template updated successfully");
      return response.data;
    } catch {
      return null;
    } finally {
      set({ loading: false });
    }
  },

  deleteTemplate: async (id: string) => {
    set({ loading: true });
    try {
      await templateApi.delete(id);
      message.success("Template deleted successfully");
      return true;
    } catch {
      return false;
    } finally {
      set({ loading: false });
    }
  },

  cloneTemplate: async (id: string, data?: TemplateClone) => {
    set({ loading: true });
    try {
      const response = await templateApi.clone(id, data);
      message.success("Template cloned successfully");
      return response.data;
    } catch {
      return null;
    } finally {
      set({ loading: false });
    }
  },

  clearCurrentTemplate: () => set({ currentTemplate: null }),
}));
