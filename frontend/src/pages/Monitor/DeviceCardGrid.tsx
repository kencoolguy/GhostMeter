import type { DeviceMonitorData, RegisterHistoryPoint } from "../../types";
import { DeviceCard } from "./DeviceCard";

interface DeviceCardGridProps {
  devices: DeviceMonitorData[];
  registerHistory: Record<string, RegisterHistoryPoint[]>;
}

const PREFERRED = ["total_power", "ac_power", "total_energy"];

function pickPrimaryName(device: DeviceMonitorData): string | null {
  const names = device.registers.map((r) => r.name);
  return PREFERRED.find((n) => names.includes(n)) ?? names[0] ?? null;
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
