import { Badge, Button, Typography } from "antd";
import { useCallback, useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { useWebSocket } from "../../hooks/useWebSocket";
import { MONITOR_WS_URL } from "../../services/ws";
import { useMonitorStore } from "../../stores/monitorStore";
import type { MonitorUpdate } from "../../types";
import { DeviceCardGrid } from "./DeviceCardGrid";
import { EmptyState } from "./EmptyState";
import { EventDrawer } from "./EventDrawer";
import { EventToast } from "./EventToast";
import { KpiPanel } from "./KpiPanel";
import "./monitor.css";

export default function MonitorPage() {
  const {
    devices,
    events,
    registerHistory,
    mqttBrokerConnected,
    recentToastEvent,
    eventDrawerOpen,
    handleMonitorUpdate,
    dismissToast,
    openEventDrawer,
    closeEventDrawer,
    clearEvents,
  } = useMonitorStore();

  const onMessage = useCallback(
    (data: unknown) => {
      const update = data as MonitorUpdate;
      if (update.type === "monitor_update") {
        handleMonitorUpdate(update);
      }
    },
    [handleMonitorUpdate],
  );

  const { connected } = useWebSocket({ url: MONITOR_WS_URL, onMessage });

  // "Open in Monitor" from DeviceDetail passes ?device=<id>: scroll the
  // matching card into view once it arrives in the broadcast, then drop
  // the param so refreshes don't re-scroll.
  const [searchParams, setSearchParams] = useSearchParams();
  const focusDeviceId = searchParams.get("device");
  useEffect(() => {
    if (!focusDeviceId || devices.length === 0) return;
    const el = document.getElementById(`gm-device-card-${focusDeviceId}`);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      setSearchParams({}, { replace: true });
    }
  }, [focusDeviceId, devices, setSearchParams]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <Typography.Title level={2} style={{ margin: 0 }}>
          Monitor{" "}
          <Badge
            status={connected ? "success" : "error"}
            text={<span style={{ fontSize: 12 }}>{connected ? "Live" : "Disconnected"}</span>}
            style={{ marginLeft: 10 }}
          />
        </Typography.Title>
        <Button onClick={openEventDrawer}>
          📋 Events <span style={{ marginLeft: 4, color: "var(--gm-text-2)" }}>({events.length})</span>
        </Button>
      </div>

      {devices.length === 0 ? (
        <EmptyState />
      ) : (
        <>
          <KpiPanel devices={devices} mqttBrokerConnected={mqttBrokerConnected} />
          <DeviceCardGrid devices={devices} registerHistory={registerHistory} />
        </>
      )}

      <EventToast
        event={recentToastEvent}
        onDismiss={dismissToast}
        onOpenDrawer={() => {
          dismissToast();
          openEventDrawer();
        }}
      />

      <EventDrawer
        open={eventDrawerOpen}
        events={events}
        onClose={closeEventDrawer}
        onClear={clearEvents}
      />
    </div>
  );
}
