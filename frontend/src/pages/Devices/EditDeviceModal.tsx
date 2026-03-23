import { Form, Input, InputNumber, Modal, Tooltip } from "antd";
import { useEffect } from "react";
import type { DeviceSummary, UpdateDevice } from "../../types";
import { useDeviceStore } from "../../stores/deviceStore";

interface EditDeviceModalProps {
  open: boolean;
  device: DeviceSummary | null;
  onClose: () => void;
  onSuccess: () => void;
}

export function EditDeviceModal({ open, device, onClose, onSuccess }: EditDeviceModalProps) {
  const [form] = Form.useForm<UpdateDevice>();
  const { updateDevice, loading } = useDeviceStore();

  useEffect(() => {
    if (open && device) {
      form.setFieldsValue({
        name: device.name,
        slave_id: device.slave_id,
        port: device.port,
        description: device.description,
      });
    }
  }, [open, device, form]);

  const isRunning = device?.status === "running";

  const handleSubmit = async () => {
    if (!device) return;
    const values = await form.validateFields();
    const result = await updateDevice(device.id, values);
    if (result) {
      onSuccess();
      onClose();
    }
  };

  return (
    <Modal
      title="Edit Device"
      open={open}
      onOk={handleSubmit}
      onCancel={onClose}
      confirmLoading={loading}
      destroyOnClose
    >
      <Form form={form} layout="vertical">
        <Form.Item
          name="name"
          label="Device Name"
          rules={[{ required: true, message: "Please enter device name" }]}
        >
          <Input />
        </Form.Item>
        <Tooltip title={isRunning ? "Stop the device before changing Slave ID" : undefined}>
          <Form.Item
            name="slave_id"
            label="Slave ID"
            rules={[{ required: true, message: "Please enter Slave ID" }]}
          >
            <InputNumber min={1} max={247} style={{ width: "100%" }} disabled={isRunning} />
          </Form.Item>
        </Tooltip>
        <Tooltip title={isRunning ? "Stop the device before changing Port" : undefined}>
          <Form.Item
            name="port"
            label="Port"
            rules={[{ required: true, message: "Please enter port" }]}
          >
            <InputNumber min={1} max={65535} style={{ width: "100%" }} disabled={isRunning} />
          </Form.Item>
        </Tooltip>
        <Form.Item name="description" label="Description">
          <Input.TextArea rows={2} />
        </Form.Item>
      </Form>
    </Modal>
  );
}
