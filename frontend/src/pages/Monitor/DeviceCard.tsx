import { Badge, Card, Space, Tag, Typography } from "antd";
import type { DeviceMonitorData } from "../../types";

const { Text } = Typography;

interface DeviceCardProps {
  device: DeviceMonitorData;
  selected: boolean;
  onClick: () => void;
}

const STATUS_COLORS: Record<string, string> = {
  running: "#52c41a",
  error: "#ff4d4f",
  stopped: "#d9d9d9",
};

export function DeviceCard({ device, selected, onClick }: DeviceCardProps) {
  const statusColor = STATUS_COLORS[device.status] ?? "#d9d9d9";
  const preferred = ["total_power", "total_energy"];
  const keyRegisters = (() => {
    const matched = preferred.flatMap((name) => {
      const reg = device.registers.find((r) => r.name === name);
      return reg ? [reg] : [];
    });
    return matched.length > 0 ? matched : device.registers.slice(0, 2);
  })();

  return (
    <Card
      hoverable
      onClick={onClick}
      style={{
        borderColor: selected ? "#1677ff" : undefined,
        borderWidth: selected ? 2 : 1,
      }}
      size="small"
    >
      <Space direction="vertical" size={4} style={{ width: "100%" }}>
        <Space>
          <Badge color={statusColor} />
          <Text strong>{device.name}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>
            ID:{device.slave_id}
          </Text>
        </Space>

        {keyRegisters.map((reg) => (
          <div key={reg.name} style={{ fontSize: 13 }}>
            <Text type="secondary">{reg.name}: </Text>
            <Text>
              {typeof reg.value === "number" ? reg.value.toFixed(1) : "—"}{" "}
              {reg.unit}
            </Text>
          </div>
        ))}

        <Space size={4} wrap>
          {device.active_anomalies.length > 0 && (
            <Tag color="orange">
              {device.active_anomalies.length} anomal{device.active_anomalies.length === 1 ? "y" : "ies"}
            </Tag>
          )}
          {device.active_fault && (
            <Tag color="red">
              {device.active_fault.fault_type}
            </Tag>
          )}
        </Space>
      </Space>
    </Card>
  );
}
