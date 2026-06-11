import { message } from "antd";
import { create } from "zustand";
import { scenarioApi } from "../services/scenarioApi";
import type { ScenarioDetail, ScenarioSummary } from "../types/scenario";

interface ScenarioState {
  scenarios: ScenarioSummary[];
  currentScenario: ScenarioDetail | null;
  loading: boolean;
  fetchScenarios: (templateId?: string) => Promise<void>;
  fetchScenario: (id: string) => Promise<void>;
  deleteScenario: (id: string) => Promise<boolean>;
  clearCurrentScenario: () => void;
}

export const useScenarioStore = create<ScenarioState>((set) => ({
  scenarios: [],
  currentScenario: null,
  loading: false,

  fetchScenarios: async (templateId) => {
    set({ loading: true });
    try {
      const resp = await scenarioApi.list(templateId);
      set({ scenarios: resp.data ?? [] });
    } catch {
      message.error("Failed to load scenarios");
    } finally {
      set({ loading: false });
    }
  },

  fetchScenario: async (id) => {
    set({ loading: true });
    try {
      const resp = await scenarioApi.get(id);
      set({ currentScenario: resp.data ?? null });
    } catch {
      message.error("Failed to load scenario");
    } finally {
      set({ loading: false });
    }
  },

  deleteScenario: async (id) => {
    try {
      await scenarioApi.delete(id);
      message.success("Scenario deleted");
      return true;
    } catch {
      message.error("Failed to delete scenario");
      return false;
    }
  },

  clearCurrentScenario: () => set({ currentScenario: null }),
}));
