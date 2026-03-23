import { Select, Tabs, Typography } from "antd";
import { useEffect } from "react";
import { useDeviceStore } from "../../stores/deviceStore";
import { useSimulationStore } from "../../stores/simulationStore";
import { AnomalyTab } from "./AnomalyTab";
import { DataModeTab } from "./DataModeTab";
import { FaultTab } from "./FaultTab";

export default function SimulationPage() {
  const { devices, fetchDevices } = useDeviceStore();
  const { selectedDeviceId, setSelectedDevice } = useSimulationStore();

  useEffect(() => {
    fetchDevices();
  }, [fetchDevices]);

  const deviceOptions = devices.map((d) => ({
    value: d.id,
    label: `${d.name} (Slave ${d.slave_id})`,
  }));

  const handleDeviceChange = (deviceId: string) => {
    setSelectedDevice(deviceId);
  };

  const tabItems = [
    {
      key: "data_mode",
      label: "Data Mode",
      children: selectedDeviceId ? (
        <DataModeTab deviceId={selectedDeviceId} />
      ) : null,
    },
    {
      key: "anomaly",
      label: "Anomaly",
      children: selectedDeviceId ? (
        <AnomalyTab deviceId={selectedDeviceId} />
      ) : null,
    },
    {
      key: "fault",
      label: "Fault",
      children: selectedDeviceId ? (
        <FaultTab deviceId={selectedDeviceId} />
      ) : null,
    },
  ];

  return (
    <div>
      <Typography.Title level={2}>Simulation Control</Typography.Title>

      <div style={{ marginBottom: 16 }}>
        <Typography.Text strong style={{ marginRight: 8 }}>
          Device:
        </Typography.Text>
        <Select
          placeholder="Select a device"
          value={selectedDeviceId ?? undefined}
          options={deviceOptions}
          onChange={handleDeviceChange}
          style={{ width: 320 }}
          allowClear
          onClear={() => setSelectedDevice(null)}
        />
      </div>

      <Tabs
        items={tabItems}
        defaultActiveKey="data_mode"
      />
    </div>
  );
}
