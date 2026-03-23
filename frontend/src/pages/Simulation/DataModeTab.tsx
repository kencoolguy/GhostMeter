import { Button, Input, InputNumber, Select, Switch, Table, message } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useCallback, useEffect, useState } from "react";
import { deviceApi } from "../../services/deviceApi";
import { useSimulationStore } from "../../stores/simulationStore";
import type { RegisterValue, SimulationConfigRequest } from "../../types";

const DATA_MODE_OPTIONS = [
  { value: "static", label: "Static" },
  { value: "random", label: "Random" },
  { value: "daily_curve", label: "Daily Curve" },
  { value: "computed", label: "Computed" },
  { value: "accumulator", label: "Accumulator" },
];

interface ConfigRow {
  key: string;
  register_name: string;
  address: number;
  data_mode: SimulationConfigRequest["data_mode"];
  mode_params: string; // JSON string for editing
  is_enabled: boolean;
  update_interval_ms: number;
}

export function DataModeTab({ deviceId }: { deviceId: string }) {
  const { configs, loading, fetchConfigs, saveConfigs } = useSimulationStore();
  const [registers, setRegisters] = useState<RegisterValue[]>([]);
  const [rows, setRows] = useState<ConfigRow[]>([]);

  const loadRegisters = useCallback(async () => {
    try {
      const response = await deviceApi.get(deviceId);
      setRegisters(response.data?.registers ?? []);
    } catch {
      message.error("Failed to load device registers");
    }
  }, [deviceId]);

  useEffect(() => {
    loadRegisters();
    fetchConfigs(deviceId);
  }, [deviceId, loadRegisters, fetchConfigs]);

  // Build rows when registers or configs change
  useEffect(() => {
    if (registers.length === 0) return;

    const configMap = new Map(configs.map((c) => [c.register_name, c]));

    const newRows: ConfigRow[] = registers.map((reg) => {
      const existing = configMap.get(reg.name);
      return {
        key: reg.name,
        register_name: reg.name,
        address: reg.address,
        data_mode: existing?.data_mode ?? "static",
        mode_params: existing ? JSON.stringify(existing.mode_params, null, 2) : "{}",
        is_enabled: existing?.is_enabled ?? false,
        update_interval_ms: existing?.update_interval_ms ?? 1000,
      };
    });
    setRows(newRows);
  }, [registers, configs]);

  const updateRow = (key: string, field: keyof ConfigRow, value: unknown) => {
    setRows((prev) =>
      prev.map((r) => (r.key === key ? { ...r, [field]: value } : r)),
    );
  };

  const handleSave = async () => {
    const configRequests: SimulationConfigRequest[] = [];
    for (const row of rows) {
      let parsedParams: Record<string, unknown>;
      try {
        parsedParams = JSON.parse(row.mode_params);
      } catch {
        message.error(`Invalid JSON in params for register "${row.register_name}"`);
        return;
      }
      configRequests.push({
        register_name: row.register_name,
        data_mode: row.data_mode,
        mode_params: parsedParams,
        is_enabled: row.is_enabled,
        update_interval_ms: row.update_interval_ms,
      });
    }
    await saveConfigs(deviceId, { configs: configRequests });
  };

  const columns: ColumnsType<ConfigRow> = [
    {
      title: "Register",
      dataIndex: "register_name",
      key: "register_name",
      width: 180,
      render: (name: string, record) => (
        <span>
          {name}{" "}
          <span style={{ color: "#999", fontSize: 12 }}>@{record.address}</span>
        </span>
      ),
    },
    {
      title: "Data Mode",
      dataIndex: "data_mode",
      key: "data_mode",
      width: 160,
      render: (value: string, record) => (
        <Select
          value={value}
          options={DATA_MODE_OPTIONS}
          style={{ width: "100%" }}
          onChange={(v) => updateRow(record.key, "data_mode", v)}
        />
      ),
    },
    {
      title: "Parameters (JSON)",
      dataIndex: "mode_params",
      key: "mode_params",
      render: (value: string, record) => (
        <Input.TextArea
          value={value}
          rows={2}
          style={{ fontFamily: "monospace", fontSize: 12 }}
          onChange={(e) => updateRow(record.key, "mode_params", e.target.value)}
        />
      ),
    },
    {
      title: "Interval (ms)",
      dataIndex: "update_interval_ms",
      key: "update_interval_ms",
      width: 120,
      render: (value: number, record) => (
        <InputNumber
          value={value}
          min={100}
          step={100}
          style={{ width: "100%" }}
          onChange={(v) => updateRow(record.key, "update_interval_ms", v ?? 1000)}
        />
      ),
    },
    {
      title: "Enabled",
      dataIndex: "is_enabled",
      key: "is_enabled",
      width: 80,
      align: "center",
      render: (value: boolean, record) => (
        <Switch
          checked={value}
          onChange={(v) => updateRow(record.key, "is_enabled", v)}
        />
      ),
    },
  ];

  return (
    <div>
      <Table
        columns={columns}
        dataSource={rows}
        rowKey="key"
        loading={loading}
        pagination={false}
        size="small"
      />
      <div style={{ marginTop: 16, display: "flex", justifyContent: "flex-end" }}>
        <Button type="primary" onClick={handleSave} loading={loading}>
          Save All
        </Button>
      </div>
    </div>
  );
}
