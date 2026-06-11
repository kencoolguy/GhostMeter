import { create } from "zustand";
import type {
  DeviceMonitorData,
  MonitorEvent,
  MonitorUpdate,
  RegisterHistoryPoint,
} from "../types";
import { pickPrimaryName } from "../utils/pickPrimary";

const MAX_HISTORY_POINTS = 300; // 5 minutes at 1Hz
const TOAST_EVENT_TYPES = new Set([
  "anomaly_inject",
  "fault_set",
  "device_start",
  "device_stop",
]);

// key: `${deviceId}:${registerName}`
type RegisterHistoryMap = Record<string, RegisterHistoryPoint[]>;

interface MonitorState {
  devices: DeviceMonitorData[];
  events: MonitorEvent[];
  registerHistory: RegisterHistoryMap;
  mqttBrokerConnected: boolean;
  recentToastEvent: MonitorEvent | null;
  eventDrawerOpen: boolean;

  handleMonitorUpdate: (update: MonitorUpdate) => void;
  dismissToast: () => void;
  openEventDrawer: () => void;
  closeEventDrawer: () => void;
  clearEvents: () => void;
}

function findNewestEventNotIn(
  next: MonitorEvent[],
  prev: MonitorEvent[],
): MonitorEvent | null {
  // Backend returns events newest-first (see monitor_service.get_events).
  // An event is "new" if its (timestamp, device_id, event_type) tuple is not in prev.
  if (next.length === 0) return null;
  const prevKeys = new Set(
    prev.map((e) => `${e.timestamp}|${e.device_id}|${e.event_type}`),
  );
  for (const e of next) {
    const key = `${e.timestamp}|${e.device_id}|${e.event_type}`;
    if (!prevKeys.has(key) && TOAST_EVENT_TYPES.has(e.event_type)) {
      return e;
    }
  }
  return null;
}

export const useMonitorStore = create<MonitorState>((set) => ({
  devices: [],
  events: [],
  registerHistory: {},
  mqttBrokerConnected: false,
  recentToastEvent: null,
  eventDrawerOpen: false,

  handleMonitorUpdate: (update: MonitorUpdate) => {
    set((state) => {
      const now = Date.now();
      const newHistory = { ...state.registerHistory };

      // Only the primary register of running devices feeds a sparkline;
      // tracking every register would copy N×300-point arrays each second
      // for data nothing reads.
      for (const device of update.devices) {
        if (device.status !== "running") continue;
        const primaryName = pickPrimaryName(device);
        const reg = device.registers.find((r) => r.name === primaryName);
        if (!reg) continue;
        const key = `${device.device_id}:${reg.name}`;
        const existing = newHistory[key] ?? [];
        const updated = [...existing, { timestamp: now, value: reg.value }];
        newHistory[key] =
          updated.length > MAX_HISTORY_POINTS
            ? updated.slice(updated.length - MAX_HISTORY_POINTS)
            : updated;
      }

      const newToast = findNewestEventNotIn(update.events, state.events);

      return {
        devices: update.devices,
        events: update.events,
        registerHistory: newHistory,
        mqttBrokerConnected: update.mqtt_broker_connected,
        ...(newToast !== null ? { recentToastEvent: newToast } : {}),
      };
    });
  },

  dismissToast: () => set({ recentToastEvent: null }),
  openEventDrawer: () => set({ eventDrawerOpen: true }),
  closeEventDrawer: () => set({ eventDrawerOpen: false }),
  clearEvents: () => set({ events: [] }),
}));
