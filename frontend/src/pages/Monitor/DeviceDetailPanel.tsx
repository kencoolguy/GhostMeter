import { Card, Select, Space, Table, Tag, Typography } from "antd";
import { useState } from "react";
import type { DeviceMonitorData, RegisterHistoryPoint } from "../../types";
import { RegisterChart } from "./RegisterChart";
import { StatsPanel } from "./StatsPanel";

const { Text } = Typography;

interface DeviceDetailPanelProps {
  device: DeviceMonitorData;
  registerHistory: Record<string, RegisterHistoryPoint[]>;
}

export function DeviceDetailPanel({
  device,
  registerHistory,
}: DeviceDetailPanelProps) {
  const [chartRegister, setChartRegister] = useState<string>(
    device.registers[0]?.name ?? "",
  );

  const selectedReg = device.registers.find((r) => r.name === chartRegister);
  const historyKey = `${device.device_id}:${chartRegister}`;
  const history = registerHistory[historyKey] ?? [];

  const columns = [
    {
      title: "Register",
      dataIndex: "name",
      key: "name",
      width: 200,
    },
    {
      title: "Value",
      dataIndex: "value",
      key: "value",
      render: (v: number) => (typeof v === "number" ? v.toFixed(2) : "—"),
    },
    {
      title: "Unit",
      dataIndex: "unit",
      key: "unit",
      width: 80,
    },
  ];

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Card
        title={`${device.name} — Registers`}
        size="small"
        extra={
          <Space>
            {device.active_anomalies.map((a) => (
              <Tag key={a} color="orange">{a}</Tag>
            ))}
            {device.active_fault && (
              <Tag color="red">Fault: {device.active_fault.fault_type}</Tag>
            )}
          </Space>
        }
      >
        <Table
          dataSource={device.registers}
          columns={columns}
          rowKey="name"
          size="small"
          pagination={false}
        />
      </Card>

      <Card title="Register Chart" size="small">
        <Space style={{ marginBottom: 12 }}>
          <Text>Register:</Text>
          <Select
            value={chartRegister}
            onChange={setChartRegister}
            style={{ width: 200 }}
            options={device.registers.map((r) => ({
              label: `${r.name} (${r.unit})`,
              value: r.name,
            }))}
          />
        </Space>
        <RegisterChart
          history={history}
          registerName={chartRegister}
          unit={selectedReg?.unit ?? ""}
        />
      </Card>

      <Card title="Communication Stats" size="small">
        <StatsPanel stats={device.stats} />
      </Card>
    </Space>
  );
}
