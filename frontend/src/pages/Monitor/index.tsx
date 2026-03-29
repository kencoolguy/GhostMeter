import { Badge, Collapse, Space, Typography } from "antd";
import { useCallback, useEffect, useRef } from "react";
import { useSearchParams } from "react-router-dom";
import { useWebSocket } from "../../hooks/useWebSocket";
import { useMonitorStore } from "../../stores/monitorStore";
import type { MonitorUpdate } from "../../types";
import { DeviceCardGrid } from "./DeviceCardGrid";
import { DeviceDetailPanel } from "./DeviceDetailPanel";
import { EventLog } from "./EventLog";

const WS_URL = `ws://${window.location.hostname}:8000/ws/monitor`;

export default function MonitorPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const autoSelectApplied = useRef(false);
  const {
    devices,
    events,
    registerHistory,
    selectedDeviceId,
    handleMonitorUpdate,
    selectDevice,
  } = useMonitorStore();

  // Auto-select device from ?device= query param (once devices are loaded)
  useEffect(() => {
    const deviceParam = searchParams.get("device");
    if (deviceParam && devices.length > 0 && !autoSelectApplied.current) {
      const exists = devices.some((d) => d.device_id === deviceParam);
      if (exists) {
        selectDevice(deviceParam);
      }
      // Clear the query param so it doesn't persist on manual navigation
      searchParams.delete("device");
      setSearchParams(searchParams, { replace: true });
      autoSelectApplied.current = true;
    }
  }, [searchParams, setSearchParams, devices, selectDevice]);

  const onMessage = useCallback(
    (data: unknown) => {
      const update = data as MonitorUpdate;
      if (update.type === "monitor_update") {
        handleMonitorUpdate(update);
      }
    },
    [handleMonitorUpdate],
  );

  const { connected } = useWebSocket({ url: WS_URL, onMessage });

  const selectedDevice = devices.find((d) => d.device_id === selectedDeviceId);

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Space>
        <Typography.Title level={2} style={{ margin: 0 }}>
          Real-time Monitor
        </Typography.Title>
        <Badge
          status={connected ? "success" : "error"}
          text={connected ? "Connected" : "Disconnected"}
        />
      </Space>

      <DeviceCardGrid
        devices={devices}
        selectedDeviceId={selectedDeviceId}
        onSelectDevice={selectDevice}
      />

      {selectedDevice && (
        <DeviceDetailPanel
          device={selectedDevice}
          registerHistory={registerHistory}
        />
      )}

      <Collapse
        items={[
          {
            key: "events",
            label: `Event Log (${events.length})`,
            children: <EventLog events={events} />,
          },
        ]}
        defaultActiveKey={["events"]}
      />
    </Space>
  );
}
