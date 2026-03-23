import { Flex } from "antd";
import type { DeviceMonitorData } from "../../types";
import { DeviceCard } from "./DeviceCard";

interface DeviceCardGridProps {
  devices: DeviceMonitorData[];
  selectedDeviceId: string | null;
  onSelectDevice: (deviceId: string) => void;
}

export function DeviceCardGrid({
  devices,
  selectedDeviceId,
  onSelectDevice,
}: DeviceCardGridProps) {
  if (devices.length === 0) {
    return (
      <div style={{ textAlign: "center", padding: 40, color: "#999" }}>
        No running devices. Start a device to see live data.
      </div>
    );
  }

  return (
    <Flex wrap gap={16}>
      {devices.map((device) => (
        <div key={device.device_id} style={{ width: 280 }}>
          <DeviceCard
            device={device}
            selected={device.device_id === selectedDeviceId}
            onClick={() => onSelectDevice(device.device_id)}
          />
        </div>
      ))}
    </Flex>
  );
}
