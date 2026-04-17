import type { DeviceMonitorData, RegisterHistoryPoint } from "../../types";
import { DeviceCard } from "./DeviceCard";
import { pickPrimaryName } from "./pickPrimary";

interface DeviceCardGridProps {
  devices: DeviceMonitorData[];
  registerHistory: Record<string, RegisterHistoryPoint[]>;
}

export function DeviceCardGrid({ devices, registerHistory }: DeviceCardGridProps) {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))",
        gap: 12,
      }}
    >
      {devices.map((device) => {
        const primary = pickPrimaryName(device);
        const history = primary
          ? registerHistory[`${device.device_id}:${primary}`] ?? []
          : [];
        return <DeviceCard key={device.device_id} device={device} history={history} />;
      })}
    </div>
  );
}
