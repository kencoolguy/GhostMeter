import { create } from "zustand";
import type {
  DeviceMonitorData,
  MonitorEvent,
  MonitorUpdate,
  RegisterHistoryPoint,
} from "../types";

const MAX_HISTORY_POINTS = 300; // 5 minutes at 1Hz

// key: `${deviceId}:${registerName}`
type RegisterHistoryMap = Record<string, RegisterHistoryPoint[]>;

interface MonitorState {
  devices: DeviceMonitorData[];
  events: MonitorEvent[];
  registerHistory: RegisterHistoryMap;
  selectedDeviceId: string | null;

  handleMonitorUpdate: (update: MonitorUpdate) => void;
  selectDevice: (deviceId: string | null) => void;
}

export const useMonitorStore = create<MonitorState>((set) => ({
  devices: [],
  events: [],
  registerHistory: {},
  selectedDeviceId: null,

  handleMonitorUpdate: (update: MonitorUpdate) => {
    set((state) => {
      const now = Date.now();
      const newHistory = { ...state.registerHistory };

      for (const device of update.devices) {
        for (const reg of device.registers) {
          const key = `${device.device_id}:${reg.name}`;
          const existing = newHistory[key] ?? [];
          const updated = [
            ...existing,
            { timestamp: now, value: reg.value },
          ];
          // Trim to max points
          newHistory[key] = updated.length > MAX_HISTORY_POINTS
            ? updated.slice(updated.length - MAX_HISTORY_POINTS)
            : updated;
        }
      }

      return {
        devices: update.devices,
        events: update.events,
        registerHistory: newHistory,
      };
    });
  },

  selectDevice: (deviceId: string | null) => {
    set({ selectedDeviceId: deviceId });
  },
}));
