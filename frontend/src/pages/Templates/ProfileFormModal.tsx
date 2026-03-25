import {
  Form,
  Input,
  InputNumber,
  Modal,
  Select,
  Switch,
  Table,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { useEffect, useState } from "react";
import { useProfileStore } from "../../stores/profileStore";
import type {
  DataMode,
  ProfileConfigEntry,
  RegisterDefinition,
  SimulationProfile,
} from "../../types";

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
  data_mode: DataMode;
  mode_params: string;
  is_enabled: boolean;
  update_interval_ms: number;
}

interface ProfileFormModalProps {
  open: boolean;
  onClose: () => void;
  templateId: string;
  registers: Omit<RegisterDefinition, "id">[];
  profile?: SimulationProfile | null;
}

export function ProfileFormModal({
  open,
  onClose,
  templateId,
  registers,
  profile,
}: ProfileFormModalProps) {
  const [form] = Form.useForm();
  const { createProfile, updateProfile, fetchProfiles, loading } =
    useProfileStore();
  const [rows, setRows] = useState<ConfigRow[]>([]);

  const isEdit = Boolean(profile);
  const isBuiltinConfigs = Boolean(profile?.is_builtin);

  useEffect(() => {
    if (!open) return;

    if (profile) {
      form.setFieldsValue({
        name: profile.name,
        description: profile.description,
      });
    } else {
      form.resetFields();
    }

    // Build config rows from template registers
    const configMap = new Map(
      (profile?.configs ?? []).map((c) => [c.register_name, c]),
    );

    const newRows: ConfigRow[] = registers.map((reg) => {
      const existing = configMap.get(reg.name);
      return {
        key: reg.name,
        register_name: reg.name,
        data_mode: (existing?.data_mode as DataMode) ?? "static",
        mode_params: existing
          ? JSON.stringify(existing.mode_params, null, 2)
          : "{}",
        is_enabled: existing?.is_enabled ?? true,
        update_interval_ms: existing?.update_interval_ms ?? 1000,
      };
    });
    setRows(newRows);
  }, [open, profile, registers, form]);

  const updateRow = (key: string, field: keyof ConfigRow, value: unknown) => {
    setRows((prev) =>
      prev.map((r) => (r.key === key ? { ...r, [field]: value } : r)),
    );
  };

  const handleSubmit = async () => {
    const values = await form.validateFields();

    // Parse config rows
    const configs: ProfileConfigEntry[] = [];
    for (const row of rows) {
      let parsedParams: Record<string, unknown>;
      try {
        parsedParams = JSON.parse(row.mode_params);
      } catch {
        message.error(
          `Invalid JSON in params for register "${row.register_name}"`,
        );
        return;
      }
      configs.push({
        register_name: row.register_name,
        data_mode: row.data_mode,
        mode_params: parsedParams,
        is_enabled: row.is_enabled,
        update_interval_ms: row.update_interval_ms,
      });
    }

    let success: boolean;
    if (isEdit && profile) {
      const updateData = isBuiltinConfigs
        ? { name: values.name, description: values.description }
        : { name: values.name, description: values.description, configs };
      success = await updateProfile(profile.id, updateData);
    } else {
      success = await createProfile({
        template_id: templateId,
        name: values.name,
        description: values.description,
        configs,
      });
    }

    if (success) {
      await fetchProfiles(templateId);
      onClose();
    }
  };

  const columns: ColumnsType<ConfigRow> = [
    {
      title: "Register",
      dataIndex: "register_name",
      key: "register_name",
      width: 180,
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
          disabled={isBuiltinConfigs}
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
          disabled={isBuiltinConfigs}
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
          onChange={(v) =>
            updateRow(record.key, "update_interval_ms", v ?? 1000)
          }
          disabled={isBuiltinConfigs}
        />
      ),
    },
    {
      title: "Enabled",
      dataIndex: "is_enabled",
      key: "is_enabled",
      width: 80,
      align: "center" as const,
      render: (value: boolean, record) => (
        <Switch
          checked={value}
          onChange={(v) => updateRow(record.key, "is_enabled", v)}
          disabled={isBuiltinConfigs}
        />
      ),
    },
  ];

  return (
    <Modal
      title={isEdit ? "Edit Profile" : "New Profile"}
      open={open}
      onOk={handleSubmit}
      onCancel={onClose}
      width={900}
      destroyOnClose
      confirmLoading={loading}
    >
      <Form form={form} layout="vertical" style={{ marginBottom: 16 }}>
        <Form.Item
          name="name"
          label="Profile Name"
          rules={[{ required: true, message: "Please enter a name" }]}
        >
          <Input placeholder="e.g. Normal Operation" />
        </Form.Item>
        <Form.Item name="description" label="Description">
          <Input.TextArea rows={2} placeholder="Optional description" />
        </Form.Item>
      </Form>

      <Table
        columns={columns}
        dataSource={rows}
        rowKey="key"
        pagination={false}
        size="small"
        scroll={{ y: 400 }}
      />
    </Modal>
  );
}
