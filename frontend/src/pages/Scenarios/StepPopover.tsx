import { Button, Form, InputNumber, Select, Space } from "antd";
import type { ScenarioStepCreate } from "../../types/scenario";

const ANOMALY_TYPES = [
  { value: "spike", label: "Spike" },
  { value: "drift", label: "Drift" },
  { value: "flatline", label: "Flatline" },
  { value: "out_of_range", label: "Out of Range" },
  { value: "data_loss", label: "Data Loss" },
];

const ANOMALY_PARAM_FIELDS: Record<string, { label: string; key: string; default: number }[]> = {
  spike: [
    { label: "Probability", key: "probability", default: 0.8 },
    { label: "Multiplier", key: "multiplier", default: 1.5 },
  ],
  drift: [
    { label: "Drift/sec", key: "drift_per_second", default: 2 },
    { label: "Max Drift", key: "max_drift", default: 30 },
  ],
  flatline: [{ label: "Value", key: "value", default: 0 }],
  out_of_range: [{ label: "Value", key: "value", default: 0 }],
  data_loss: [],
};

interface StepPopoverProps {
  registerName: string;
  initialValues?: Partial<ScenarioStepCreate>;
  onSave: (step: ScenarioStepCreate) => void;
  onDelete?: () => void;
  onCancel: () => void;
}

export function StepPopover({ registerName, initialValues, onSave, onDelete, onCancel }: StepPopoverProps) {
  const [form] = Form.useForm();
  const anomalyType = Form.useWatch("anomaly_type", form);

  const handleSave = () => {
    form.validateFields().then((values) => {
      const params: Record<string, number> = {};
      const fields = ANOMALY_PARAM_FIELDS[values.anomaly_type] ?? [];
      for (const f of fields) {
        if (values[f.key] !== undefined) params[f.key] = values[f.key];
      }
      onSave({
        register_name: registerName,
        anomaly_type: values.anomaly_type,
        anomaly_params: params,
        trigger_at_seconds: values.trigger_at_seconds,
        duration_seconds: values.duration_seconds,
        sort_order: 0,
      });
    });
  };

  const paramFields = ANOMALY_PARAM_FIELDS[anomalyType] ?? [];

  return (
    <Form
      form={form}
      layout="vertical"
      size="small"
      style={{ width: 240 }}
      initialValues={{
        anomaly_type: initialValues?.anomaly_type ?? "out_of_range",
        trigger_at_seconds: initialValues?.trigger_at_seconds ?? 0,
        duration_seconds: initialValues?.duration_seconds ?? 10,
        ...initialValues?.anomaly_params,
      }}
    >
      <Form.Item name="anomaly_type" label="Anomaly Type" rules={[{ required: true }]}>
        <Select options={ANOMALY_TYPES} />
      </Form.Item>
      {paramFields.map((f) => (
        <Form.Item key={f.key} name={f.key} label={f.label} rules={[{ required: true }]}>
          <InputNumber style={{ width: "100%" }} step={f.key === "probability" ? 0.1 : 1} />
        </Form.Item>
      ))}
      <Form.Item name="trigger_at_seconds" label="Start (seconds)" rules={[{ required: true }]}>
        <InputNumber min={0} style={{ width: "100%" }} />
      </Form.Item>
      <Form.Item name="duration_seconds" label="Duration (seconds)" rules={[{ required: true }]}>
        <InputNumber min={1} style={{ width: "100%" }} />
      </Form.Item>
      <Space>
        <Button type="primary" onClick={handleSave}>Save</Button>
        {onDelete && <Button danger onClick={onDelete}>Delete</Button>}
        <Button onClick={onCancel}>Cancel</Button>
      </Space>
    </Form>
  );
}
