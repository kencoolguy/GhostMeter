import { message } from "antd";
import { create } from "zustand";
import { deviceApi } from "../services/deviceApi";
import type {
  BatchCreateDevice,
  CreateDevice,
  DeviceDetail,
  DeviceSummary,
  UpdateDevice,
} from "../types";

interface DeviceState {
  devices: DeviceSummary[];
  currentDevice: DeviceDetail | null;
  loading: boolean;
  fetchDevices: () => Promise<void>;
  fetchDevice: (id: string) => Promise<void>;
  createDevice: (data: CreateDevice) => Promise<DeviceSummary | null>;
  batchCreateDevices: (data: BatchCreateDevice) => Promise<boolean>;
  updateDevice: (id: string, data: UpdateDevice) => Promise<DeviceSummary | null>;
  deleteDevice: (id: string) => Promise<boolean>;
  startDevice: (id: string) => Promise<boolean>;
  stopDevice: (id: string) => Promise<boolean>;
  clearCurrentDevice: () => void;
}

export const useDeviceStore = create<DeviceState>((set) => ({
  devices: [],
  currentDevice: null,
  loading: false,

  fetchDevices: async () => {
    set({ loading: true });
    try {
      const response = await deviceApi.list();
      set({ devices: response.data ?? [] });
    } finally {
      set({ loading: false });
    }
  },

  fetchDevice: async (id: string) => {
    set({ loading: true });
    try {
      const response = await deviceApi.get(id);
      set({ currentDevice: response.data });
    } finally {
      set({ loading: false });
    }
  },

  createDevice: async (data: CreateDevice) => {
    set({ loading: true });
    try {
      const response = await deviceApi.create(data);
      message.success("Device created successfully");
      return response.data;
    } catch {
      return null;
    } finally {
      set({ loading: false });
    }
  },

  batchCreateDevices: async (data: BatchCreateDevice) => {
    set({ loading: true });
    try {
      await deviceApi.batchCreate(data);
      message.success("Devices created successfully");
      return true;
    } catch {
      return false;
    } finally {
      set({ loading: false });
    }
  },

  updateDevice: async (id: string, data: UpdateDevice) => {
    set({ loading: true });
    try {
      const response = await deviceApi.update(id, data);
      message.success("Device updated successfully");
      return response.data;
    } catch {
      return null;
    } finally {
      set({ loading: false });
    }
  },

  deleteDevice: async (id: string) => {
    set({ loading: true });
    try {
      await deviceApi.delete(id);
      message.success("Device deleted successfully");
      return true;
    } catch {
      return false;
    } finally {
      set({ loading: false });
    }
  },

  startDevice: async (id: string) => {
    try {
      await deviceApi.start(id);
      return true;
    } catch {
      return false;
    }
  },

  stopDevice: async (id: string) => {
    try {
      await deviceApi.stop(id);
      return true;
    } catch {
      return false;
    }
  },

  clearCurrentDevice: () => set({ currentDevice: null }),
}));
