import { Button, Form, InputNumber, Select, Space } from "antd";
import { ANOMALY_PARAM_FIELDS, ANOMALY_TYPE_OPTIONS } from "../../constants/anomaly";
import type { AnomalyType } from "../../types";
import type { ScenarioStepCreate } from "../../types/scenario";

interface StepPopoverProps {
  registerName: string;
  initialValues?: Partial<ScenarioStepCreate>;
  onSave: (step: ScenarioStepCreate) => void;
  onDelete?: () => void;
  onCancel: () => void;
}

export function StepPopover({ registerName, initialValues, onSave, onDelete, onCancel }: StepPopoverProps) {
  const [form] = Form.useForm();
  const anomalyType = Form.useWatch("anomaly_type", form) as AnomalyType | undefined;

  const handleSave = () => {
    form.validateFields().then((values) => {
      const params: Record<string, number> = {};
      const fields = ANOMALY_PARAM_FIELDS[values.anomaly_type as AnomalyType] ?? [];
      for (const f of fields) {
        if (values[f.name] !== undefined && values[f.name] !== null) params[f.name] = values[f.name];
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

  const paramFields = anomalyType ? ANOMALY_PARAM_FIELDS[anomalyType] ?? [] : [];

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
        <Select options={ANOMALY_TYPE_OPTIONS} />
      </Form.Item>
      {paramFields.map((f) => (
        <Form.Item
          key={f.name}
          name={f.name}
          label={f.label}
          rules={f.required ? [{ required: true }] : []}
          initialValue={f.default}
        >
          <InputNumber
            min={f.min}
            max={f.max}
            step={f.step}
            placeholder={f.placeholder}
            style={{ width: "100%" }}
          />
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
