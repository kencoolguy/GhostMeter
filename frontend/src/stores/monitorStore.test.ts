import { describe, it, expect, beforeEach } from "vitest";
import { useMonitorStore } from "./monitorStore";
import type { DeviceMonitorData, MonitorEvent, MonitorUpdate } from "../types";

function device(overrides: Partial<DeviceMonitorData> = {}): DeviceMonitorData {
  return {
    device_id: "d1", name: "D1", template_name: null, slave_id: 1, port: 502,
    status: "running",
    registers: [{ name: "total_power", value: 42, unit: "W" }],
    active_anomalies: [], active_fault: null,
    stats: { request_count: 0, success_count: 0, error_count: 0, avg_response_ms: 0 },
    mqtt_stats: null, write_events: { unread: 0, latest: null },
    ...overrides,
  };
}

function update(overrides: Partial<MonitorUpdate> = {}): MonitorUpdate {
  return {
    type: "monitor_update", timestamp: "t", devices: [device()],
    events: [], mqtt_broker_connected: false, ...overrides,
  };
}

const initialState = useMonitorStore.getState();
beforeEach(() => {
  useMonitorStore.setState(initialState, true);
});

describe("monitorStore.handleMonitorUpdate", () => {
  it("stores devices and appends a history point for the primary register", () => {
    useMonitorStore.getState().handleMonitorUpdate(update());
    const s = useMonitorStore.getState();
    expect(s.devices).toHaveLength(1);
    expect(s.registerHistory["d1:total_power"]).toHaveLength(1);
    expect(s.registerHistory["d1:total_power"][0].value).toBe(42);
  });

  it("does not track history for non-running devices", () => {
    useMonitorStore.getState().handleMonitorUpdate(
      update({ devices: [device({ status: "stopped" })] }),
    );
    expect(useMonitorStore.getState().registerHistory).toEqual({});
  });

  it("caps register history at 300 points", () => {
    const store = useMonitorStore.getState();
    for (let i = 0; i < 305; i++) store.handleMonitorUpdate(update());
    expect(useMonitorStore.getState().registerHistory["d1:total_power"]).toHaveLength(300);
  });

  it("raises a toast for a new toast-worthy event", () => {
    const evt: MonitorEvent = {
      timestamp: "2026", device_id: "d1", device_name: "D1",
      event_type: "anomaly_inject", detail: "spike",
    };
    useMonitorStore.getState().handleMonitorUpdate(update({ events: [evt] }));
    expect(useMonitorStore.getState().recentToastEvent?.event_type).toBe("anomaly_inject");
  });

  it("ignores non-toast event types", () => {
    const evt: MonitorEvent = {
      timestamp: "2026", device_id: "d1", device_name: "D1",
      event_type: "register_read", detail: "",
    };
    useMonitorStore.getState().handleMonitorUpdate(update({ events: [evt] }));
    expect(useMonitorStore.getState().recentToastEvent).toBeNull();
  });
});

describe("monitorStore drawer + events", () => {
  it("opens and closes the event drawer", () => {
    useMonitorStore.getState().openEventDrawer();
    expect(useMonitorStore.getState().eventDrawerOpen).toBe(true);
    useMonitorStore.getState().closeEventDrawer();
    expect(useMonitorStore.getState().eventDrawerOpen).toBe(false);
  });

  it("clears events", () => {
    useMonitorStore.setState({
      events: [{ timestamp: "t", device_id: "d1", device_name: "D1", event_type: "x", detail: "" }],
    });
    useMonitorStore.getState().clearEvents();
    expect(useMonitorStore.getState().events).toEqual([]);
  });
});
