import { Form, Input, InputNumber, Modal, Select, Tabs } from "antd";
import { useEffect, useState } from "react";
import { useTemplateStore } from "../../stores/templateStore";
import { useDeviceStore } from "../../stores/deviceStore";
import { useProfileStore } from "../../stores/profileStore";

interface CreateDeviceModalProps {
  open: boolean;
  onClose: () => void;
}

export function CreateDeviceModal({ open, onClose }: CreateDeviceModalProps) {
  const [singleForm] = Form.useForm();
  const [batchForm] = Form.useForm();
  const [activeTab, setActiveTab] = useState("single");
  const { templates, fetchTemplates } = useTemplateStore();
  const { createDevice, batchCreateDevices, fetchDevices } = useDeviceStore();
  const { profiles, loading: profilesLoading, fetchProfiles, clearProfiles } =
    useProfileStore();
  const [selectedProfileId, setSelectedProfileId] = useState<
    string | null | undefined
  >(undefined);

  useEffect(() => {
    if (open) {
      fetchTemplates();
    }
  }, [open, fetchTemplates]);

  // Pre-select default profile when profiles load
  useEffect(() => {
    if (profiles.length > 0) {
      const defaultProfile = profiles.find((p) => p.is_default);
      setSelectedProfileId(defaultProfile?.id ?? undefined);
    } else {
      setSelectedProfileId(undefined);
    }
  }, [profiles]);

  // Clean up on close
  useEffect(() => {
    if (!open) {
      clearProfiles();
      setSelectedProfileId(undefined);
    }
  }, [open, clearProfiles]);

  const handleTemplateChange = (templateId: string) => {
    fetchProfiles(templateId);
    setSelectedProfileId(undefined);
  };

  const templateOptions = templates.map((t) => ({
    value: t.id,
    label: `${t.name} (${t.register_count} registers)`,
  }));

  const profileOptions = [
    { value: "__none__", label: "None (no profile)" },
    ...profiles.map((p) => ({
      value: p.id,
      label: `${p.name}${p.is_default ? " (default)" : ""}${p.is_builtin ? " [built-in]" : ""}`,
    })),
  ];

  const handleSingleSubmit = async () => {
    const values = await singleForm.validateFields();
    if (selectedProfileId === "__none__") {
      values.profile_id = null;
    } else if (selectedProfileId) {
      values.profile_id = selectedProfileId;
    }
    const result = await createDevice(values);
    if (result) {
      singleForm.resetFields();
      await fetchDevices();
      onClose();
    }
  };

  const handleBatchSubmit = async () => {
    const values = await batchForm.validateFields();
    if (selectedProfileId === "__none__") {
      values.profile_id = null;
    } else if (selectedProfileId) {
      values.profile_id = selectedProfileId;
    }
    const success = await batchCreateDevices(values);
    if (success) {
      batchForm.resetFields();
      await fetchDevices();
      onClose();
    }
  };

  const handleOk = () => {
    if (activeTab === "single") {
      handleSingleSubmit();
    } else {
      handleBatchSubmit();
    }
  };

  const profileDropdown = profiles.length > 0 && (
    <Form.Item label="Simulation Profile">
      <Select
        options={profileOptions}
        value={selectedProfileId ?? undefined}
        onChange={(v) => setSelectedProfileId(v)}
        placeholder={
          profilesLoading ? "Loading profiles..." : "Select profile"
        }
        loading={profilesLoading}
        disabled={profilesLoading}
        style={{ width: "100%" }}
      />
    </Form.Item>
  );

  return (
    <Modal
      title="Create Device"
      open={open}
      onOk={handleOk}
      onCancel={onClose}
      destroyOnClose
    >
      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={[
          {
            key: "single",
            label: "Single",
            children: (
              <Form form={singleForm} layout="vertical">
                <Form.Item
                  name="template_id"
                  label="Template"
                  rules={[{ required: true }]}
                >
                  <Select
                    options={templateOptions}
                    placeholder="Select template"
                    onChange={handleTemplateChange}
                  />
                </Form.Item>
                {profileDropdown}
                <Form.Item
                  name="name"
                  label="Device Name"
                  rules={[{ required: true }]}
                >
                  <Input />
                </Form.Item>
                <Form.Item
                  name="slave_id"
                  label="Slave ID"
                  rules={[{ required: true }]}
                >
                  <InputNumber min={1} max={247} style={{ width: "100%" }} />
                </Form.Item>
                <Form.Item name="description" label="Description">
                  <Input.TextArea rows={2} />
                </Form.Item>
              </Form>
            ),
          },
          {
            key: "batch",
            label: "Batch",
            children: (
              <Form form={batchForm} layout="vertical">
                <Form.Item
                  name="template_id"
                  label="Template"
                  rules={[{ required: true }]}
                >
                  <Select
                    options={templateOptions}
                    placeholder="Select template"
                    onChange={handleTemplateChange}
                  />
                </Form.Item>
                {profileDropdown}
                <Form.Item
                  name="slave_id_start"
                  label="Slave ID Start"
                  rules={[{ required: true }]}
                >
                  <InputNumber min={1} max={247} style={{ width: "100%" }} />
                </Form.Item>
                <Form.Item
                  name="slave_id_end"
                  label="Slave ID End"
                  rules={[{ required: true }]}
                >
                  <InputNumber min={1} max={247} style={{ width: "100%" }} />
                </Form.Item>
                <Form.Item name="name_prefix" label="Name Prefix (optional)">
                  <Input placeholder="Leave empty to use template name" />
                </Form.Item>
                <Form.Item name="description" label="Description">
                  <Input.TextArea rows={2} />
                </Form.Item>
              </Form>
            ),
          },
        ]}
      />
    </Modal>
  );
}
