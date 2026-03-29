import { DeleteOutlined } from "@ant-design/icons";
import {
  Button,
  Card,
  Form,
  InputNumber,
  Popconfirm,
  Select,
  Table,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { useCallback, useEffect, useState } from "react";
import { deviceApi } from "../../services/deviceApi";
import { useSimulationStore } from "../../stores/simulationStore";
import type {
  AnomalyActiveResponse,
  AnomalyScheduleResponse,
  AnomalyType,
  RegisterValue,
} from "../../types";

const ANOMALY_TYPE_OPTIONS: { value: AnomalyType; label: string }[] = [
  { value: "spike", label: "Spike" },
  { value: "drift", label: "Drift" },
  { value: "flatline", label: "Flatline" },
  { value: "out_of_range", label: "Out of Range" },
  { value: "data_loss", label: "Data Loss" },
];

interface AnomalyParamField {
  name: string;
  label: string;
  required: boolean;
  default?: number;
  min?: number;
  max?: number;
  step?: number;
  placeholder?: string;
}

const ANOMALY_PARAM_FIELDS: Record<AnomalyType, AnomalyParamField[]> = {
  spike: [
    { name: "multiplier", label: "Multiplier", required: true, default: 2.0, min: 0.01, step: 0.5 },
    { name: "probability", label: "Probability", required: true, default: 0.1, min: 0, max: 1, step: 0.1 },
  ],
  drift: [
    { name: "drift_per_second", label: "Drift/sec", required: true, step: 1, placeholder: "e.g. 10" },
    { name: "max_drift", label: "Max drift", required: true, min: 0.01, step: 10, placeholder: "e.g. 500" },
  ],
  flatline: [
    { name: "value", label: "Freeze value", required: false, placeholder: "Empty = freeze current" },
  ],
  out_of_range: [
    { name: "value", label: "Value", required: true, placeholder: "e.g. 99999" },
  ],
  data_loss: [],
};

export function AnomalyTab({ deviceId }: { deviceId: string }) {
  const {
    activeAnomalies,
    schedules,
    fetchActiveAnomalies,
    injectAnomaly,
    removeAnomaly,
    clearAnomalies,
    fetchSchedules,
    deleteSchedules,
  } = useSimulationStore();

  const [registers, setRegisters] = useState<RegisterValue[]>([]);
  const [selectedType, setSelectedType] = useState<AnomalyType | null>(null);
  const [form] = Form.useForm();

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
    fetchActiveAnomalies(deviceId);
    fetchSchedules(deviceId);
  }, [deviceId, loadRegisters, fetchActiveAnomalies, fetchSchedules]);

  const registerOptions = registers.map((r) => ({
    value: r.name,
    label: `${r.name} @${r.address}`,
  }));

  const handleTypeChange = (type: AnomalyType) => {
    setSelectedType(type);
    // Clear previous param fields and set defaults for new type
    const fields = ANOMALY_PARAM_FIELDS[type];
    const paramDefaults: Record<string, number | undefined> = {};
    for (const field of fields) {
      paramDefaults[`param_${field.name}`] = field.default;
    }
    // Clear all possible param fields first, then set new defaults
    const allParamKeys = Object.values(ANOMALY_PARAM_FIELDS)
      .flat()
      .map((f) => `param_${f.name}`);
    const clearFields: Record<string, undefined> = {};
    for (const key of allParamKeys) {
      clearFields[key] = undefined;
    }
    form.setFieldsValue({ ...clearFields, ...paramDefaults });
  };

  const handleInject = async () => {
    try {
      const values = await form.validateFields();
      const anomalyType = values.anomaly_type as AnomalyType;
      const fields = ANOMALY_PARAM_FIELDS[anomalyType];
      const params: Record<string, number> = {};
      for (const field of fields) {
        const val = values[`param_${field.name}`];
        if (val !== undefined && val !== null) {
          params[field.name] = val;
        }
      }
      const success = await injectAnomaly(deviceId, {
        register_name: values.register_name,
        anomaly_type: anomalyType,
        anomaly_params: params,
      });
      if (success) {
        form.resetFields();
        setSelectedType(null);
      }
    } catch {
      // validation failed
    }
  };

  const handleRemove = async (registerName: string) => {
    await removeAnomaly(deviceId, registerName);
  };

  const handleClearAll = async () => {
    await clearAnomalies(deviceId);
  };

  const handleDeleteSchedules = async () => {
    await deleteSchedules(deviceId);
  };

  // Active anomalies table columns
  const activeColumns: ColumnsType<AnomalyActiveResponse> = [
    { title: "Register", dataIndex: "register_name", key: "register_name" },
    { title: "Type", dataIndex: "anomaly_type", key: "anomaly_type", width: 140 },
    {
      title: "Params",
      dataIndex: "anomaly_params",
      key: "anomaly_params",
      render: (params: Record<string, unknown>) => (
        <code style={{ fontSize: 12 }}>{JSON.stringify(params)}</code>
      ),
    },
    {
      title: "Action",
      key: "action",
      width: 80,
      render: (_, record) => (
        <Popconfirm
          title="Remove this anomaly?"
          onConfirm={() => handleRemove(record.register_name)}
        >
          <Button type="text" size="small" danger icon={<DeleteOutlined />} />
        </Popconfirm>
      ),
    },
  ];

  // Schedule table columns
  const scheduleColumns: ColumnsType<AnomalyScheduleResponse> = [
    { title: "Register", dataIndex: "register_name", key: "register_name" },
    { title: "Type", dataIndex: "anomaly_type", key: "anomaly_type", width: 130 },
    {
      title: "Params",
      dataIndex: "anomaly_params",
      key: "anomaly_params",
      render: (params: Record<string, unknown>) => (
        <code style={{ fontSize: 12 }}>{JSON.stringify(params)}</code>
      ),
    },
    {
      title: "Trigger After (s)",
      dataIndex: "trigger_after_seconds",
      key: "trigger_after_seconds",
      width: 130,
      align: "center",
    },
    {
      title: "Duration (s)",
      dataIndex: "duration_seconds",
      key: "duration_seconds",
      width: 110,
      align: "center",
    },
    {
      title: "Enabled",
      dataIndex: "is_enabled",
      key: "is_enabled",
      width: 80,
      align: "center",
      render: (v: boolean) => (v ? "Yes" : "No"),
    },
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <Card title="Real-time Injection" size="small">
        <Form form={form} layout="inline" style={{ marginBottom: 16 }}>
          <Form.Item
            name="register_name"
            rules={[{ required: true, message: "Select register" }]}
          >
            <Select
              placeholder="Register"
              options={registerOptions}
              style={{ width: 200 }}
            />
          </Form.Item>
          <Form.Item
            name="anomaly_type"
            rules={[{ required: true, message: "Select type" }]}
          >
            <Select
              placeholder="Anomaly type"
              options={ANOMALY_TYPE_OPTIONS}
              style={{ width: 160 }}
              onChange={handleTypeChange}
            />
          </Form.Item>
          {selectedType &&
            ANOMALY_PARAM_FIELDS[selectedType].map((field) => (
              <Form.Item
                key={field.name}
                name={`param_${field.name}`}
                label={field.label}
                rules={field.required ? [{ required: true, message: `Required` }] : []}
                initialValue={field.default}
              >
                <InputNumber
                  min={field.min}
                  max={field.max}
                  step={field.step}
                  placeholder={field.placeholder}
                  style={{ width: 140 }}
                />
              </Form.Item>
            ))}
          <Form.Item>
            <Button type="primary" onClick={handleInject}>
              Inject
            </Button>
          </Form.Item>
        </Form>

        <Table
          columns={activeColumns}
          dataSource={activeAnomalies}
          rowKey="register_name"
          pagination={false}
          size="small"
          locale={{ emptyText: "No active anomalies" }}
        />
        {activeAnomalies.length > 0 && (
          <div style={{ marginTop: 8, display: "flex", justifyContent: "flex-end" }}>
            <Popconfirm title="Clear all anomalies?" onConfirm={handleClearAll}>
              <Button danger>Clear All</Button>
            </Popconfirm>
          </div>
        )}
      </Card>

      <Card title="Schedules" size="small">
        <Table
          columns={scheduleColumns}
          dataSource={schedules}
          rowKey="id"
          pagination={false}
          size="small"
          locale={{ emptyText: "No schedules" }}
        />
        {schedules.length > 0 && (
          <div style={{ marginTop: 8, display: "flex", justifyContent: "flex-end" }}>
            <Popconfirm title="Delete all schedules?" onConfirm={handleDeleteSchedules}>
              <Button danger>Clear Schedules</Button>
            </Popconfirm>
          </div>
        )}
      </Card>
    </div>
  );
}
