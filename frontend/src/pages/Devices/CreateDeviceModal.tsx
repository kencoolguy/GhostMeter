import { Form, Input, InputNumber, Modal, Select, Tabs } from "antd";
import { useEffect, useState } from "react";
import { useTemplateStore } from "../../stores/templateStore";
import { useDeviceStore } from "../../stores/deviceStore";

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

  useEffect(() => {
    if (open) {
      fetchTemplates();
    }
  }, [open, fetchTemplates]);

  const templateOptions = templates.map((t) => ({
    value: t.id,
    label: `${t.name} (${t.register_count} registers)`,
  }));

  const handleSingleSubmit = async () => {
    const values = await singleForm.validateFields();
    const result = await createDevice(values);
    if (result) {
      singleForm.resetFields();
      await fetchDevices();
      onClose();
    }
  };

  const handleBatchSubmit = async () => {
    const values = await batchForm.validateFields();
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
                  <Select options={templateOptions} placeholder="Select template" />
                </Form.Item>
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
                  <Select options={templateOptions} placeholder="Select template" />
                </Form.Item>
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
