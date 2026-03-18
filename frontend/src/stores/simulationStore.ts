import { message } from "antd";
import { create } from "zustand";
import { anomalyApi } from "../services/anomalyApi";
import { faultApi } from "../services/faultApi";
import { simulationApi } from "../services/simulationApi";
import type {
  AnomalyActiveResponse,
  AnomalyInjectRequest,
  AnomalyScheduleBatchSet,
  AnomalyScheduleResponse,
  FaultConfigRequest,
  FaultConfigResponse,
  SimulationConfigBatchSet,
  SimulationConfigResponse,
} from "../types";

interface SimulationState {
  selectedDeviceId: string | null;
  configs: SimulationConfigResponse[];
  activeAnomalies: AnomalyActiveResponse[];
  schedules: AnomalyScheduleResponse[];
  currentFault: FaultConfigResponse | null;
  loading: boolean;

  setSelectedDevice: (deviceId: string | null) => void;

  // Simulation configs
  fetchConfigs: (deviceId: string) => Promise<void>;
  saveConfigs: (deviceId: string, data: SimulationConfigBatchSet) => Promise<boolean>;
  deleteConfigs: (deviceId: string) => Promise<boolean>;

  // Anomaly
  fetchActiveAnomalies: (deviceId: string) => Promise<void>;
  injectAnomaly: (deviceId: string, data: AnomalyInjectRequest) => Promise<boolean>;
  removeAnomaly: (deviceId: string, registerName: string) => Promise<boolean>;
  clearAnomalies: (deviceId: string) => Promise<boolean>;

  // Schedules
  fetchSchedules: (deviceId: string) => Promise<void>;
  saveSchedules: (deviceId: string, data: AnomalyScheduleBatchSet) => Promise<boolean>;
  deleteSchedules: (deviceId: string) => Promise<boolean>;

  // Fault
  fetchFault: (deviceId: string) => Promise<void>;
  setFault: (deviceId: string, data: FaultConfigRequest) => Promise<boolean>;
  clearFault: (deviceId: string) => Promise<boolean>;
}

export const useSimulationStore = create<SimulationState>((set) => ({
  selectedDeviceId: null,
  configs: [],
  activeAnomalies: [],
  schedules: [],
  currentFault: null,
  loading: false,

  setSelectedDevice: (deviceId) => set({ selectedDeviceId: deviceId }),

  // --- Simulation Configs ---

  fetchConfigs: async (deviceId) => {
    set({ loading: true });
    try {
      const response = await simulationApi.getConfigs(deviceId);
      set({ configs: response.data ?? [] });
    } finally {
      set({ loading: false });
    }
  },

  saveConfigs: async (deviceId, data) => {
    set({ loading: true });
    try {
      const response = await simulationApi.setConfigs(deviceId, data);
      set({ configs: response.data ?? [] });
      message.success("Simulation configs saved");
      return true;
    } catch {
      return false;
    } finally {
      set({ loading: false });
    }
  },

  deleteConfigs: async (deviceId) => {
    set({ loading: true });
    try {
      await simulationApi.deleteConfigs(deviceId);
      set({ configs: [] });
      message.success("Simulation configs deleted");
      return true;
    } catch {
      return false;
    } finally {
      set({ loading: false });
    }
  },

  // --- Anomaly ---

  fetchActiveAnomalies: async (deviceId) => {
    try {
      const response = await anomalyApi.getActive(deviceId);
      set({ activeAnomalies: response.data ?? [] });
    } catch {
      /* ignore */
    }
  },

  injectAnomaly: async (deviceId, data) => {
    try {
      await anomalyApi.inject(deviceId, data);
      message.success("Anomaly injected");
      // Refresh active list
      const response = await anomalyApi.getActive(deviceId);
      set({ activeAnomalies: response.data ?? [] });
      return true;
    } catch {
      return false;
    }
  },

  removeAnomaly: async (deviceId, registerName) => {
    try {
      await anomalyApi.remove(deviceId, registerName);
      const response = await anomalyApi.getActive(deviceId);
      set({ activeAnomalies: response.data ?? [] });
      return true;
    } catch {
      return false;
    }
  },

  clearAnomalies: async (deviceId) => {
    try {
      await anomalyApi.clearAll(deviceId);
      set({ activeAnomalies: [] });
      message.success("All anomalies cleared");
      return true;
    } catch {
      return false;
    }
  },

  // --- Schedules ---

  fetchSchedules: async (deviceId) => {
    try {
      const response = await anomalyApi.getSchedules(deviceId);
      set({ schedules: response.data ?? [] });
    } catch {
      /* ignore */
    }
  },

  saveSchedules: async (deviceId, data) => {
    set({ loading: true });
    try {
      const response = await anomalyApi.setSchedules(deviceId, data);
      set({ schedules: response.data ?? [] });
      message.success("Schedules saved");
      return true;
    } catch {
      return false;
    } finally {
      set({ loading: false });
    }
  },

  deleteSchedules: async (deviceId) => {
    try {
      await anomalyApi.deleteSchedules(deviceId);
      set({ schedules: [] });
      message.success("Schedules deleted");
      return true;
    } catch {
      return false;
    }
  },

  // --- Fault ---

  fetchFault: async (deviceId) => {
    try {
      const response = await faultApi.get(deviceId);
      set({ currentFault: response.data ?? null });
    } catch {
      /* ignore */
    }
  },

  setFault: async (deviceId, data) => {
    try {
      const response = await faultApi.set(deviceId, data);
      set({ currentFault: response.data ?? null });
      message.success("Fault set");
      return true;
    } catch {
      return false;
    }
  },

  clearFault: async (deviceId) => {
    try {
      await faultApi.clear(deviceId);
      set({ currentFault: null });
      message.success("Fault cleared");
      return true;
    } catch {
      return false;
    }
  },
}));
