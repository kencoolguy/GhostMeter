import { PlayCircleOutlined, SaveOutlined, StopOutlined } from "@ant-design/icons";
import {
  Badge,
  Button,
  Card,
  Form,
  Input,
  InputNumber,
  Radio,
  Select,
  Space,
  Switch,
  Typography,
  message,
} from "antd";
import { useEffect, useState } from "react";
import { mqttApi } from "../../services/mqttApi";
import type { MqttPublishConfig as MqttConfig, MqttPublishConfigWrite } from "../../types/mqtt";

interface MqttPublishConfigProps {
  deviceId: string;
}

export function MqttPublishConfig({ deviceId }: MqttPublishConfigProps) {
  const [form] = Form.useForm<MqttPublishConfigWrite>();
  const [config, setConfig] = useState<MqttConfig | null>(null);
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);

  useEffect(() => {
    loadConfig();
  }, [deviceId]);

  const loadConfig = async () => {
    try {
      const resp = await mqttApi.getDeviceConfig(deviceId);
      if (resp.data) {
        setConfig(resp.data);
        form.setFieldsValue({
          topic_template: resp.data.topic_template,
          payload_mode: resp.data.payload_mode,
          publish_interval_seconds: resp.data.publish_interval_seconds,
          qos: resp.data.qos,
          retain: resp.data.retain,
        });
      }
    } catch {
      // No config yet
    }
  };

  const handleSave = async () => {
    setLoading(true);
    try {
      const values = await form.validateFields();
      const resp = await mqttApi.updateDeviceConfig(deviceId, values);
      if (resp.data) {
        setConfig(resp.data);
        message.success("MQTT config saved");
      }
    } catch {
      message.error("Failed to save MQTT config");
    } finally {
      setLoading(false);
    }
  };

  const handleStart = async () => {
    // Save first if no config exists
    if (!config) {
      await handleSave();
    }
    setActionLoading(true);
    try {
      const resp = await mqttApi.startPublishing(deviceId);
      if (resp.data) {
        setConfig(resp.data);
        message.success("MQTT publishing started");
      }
    } catch {
      message.error("Failed to start publishing. Check broker settings.");
    } finally {
      setActionLoading(false);
    }
  };

  const handleStop = async () => {
    setActionLoading(true);
    try {
      const resp = await mqttApi.stopPublishing(deviceId);
      if (resp.data) {
        setConfig(resp.data);
        message.success("MQTT publishing stopped");
      }
    } catch {
      message.error("Failed to stop publishing");
    } finally {
      setActionLoading(false);
    }
  };

  const isPublishing = config?.enabled ?? false;

  return (
    <Card
      title={
        <Space>
          <span>MQTT Publishing</span>
          <Badge
            status={isPublishing ? "processing" : "default"}
            text={isPublishing ? "Publishing" : "Stopped"}
          />
        </Space>
      }
      style={{ marginTop: 16 }}
    >
      <Form
        form={form}
        layout="vertical"
        initialValues={{
          topic_template: "telemetry/{device_name}",
          payload_mode: "batch",
          publish_interval_seconds: 5,
          qos: 0,
          retain: false,
        }}
      >
        <Form.Item
          name="topic_template"
          label="Topic Template"
          rules={[{ required: true, message: "Required" }]}
        >
          <Input placeholder="telemetry/{device_name}" />
        </Form.Item>
        <Typography.Text type="secondary" style={{ display: "block", marginTop: -20, marginBottom: 16, fontSize: 12 }}>
          Variables: {"{device_name}"}, {"{slave_id}"}, {"{register_name}"}, {"{template_name}"}
        </Typography.Text>

        <Form.Item name="payload_mode" label="Payload Mode">
          <Radio.Group>
            <Radio value="batch">Batch (all registers in one message)</Radio>
            <Radio value="per_register">Per Register (one message per register)</Radio>
          </Radio.Group>
        </Form.Item>

        <Form.Item
          name="publish_interval_seconds"
          label="Publish Interval (seconds)"
          rules={[{ required: true, message: "Required" }]}
        >
          <InputNumber min={1} max={3600} style={{ width: "100%" }} />
        </Form.Item>

        <Form.Item name="qos" label="QoS Level">
          <Select>
            <Select.Option value={0}>0 — At most once</Select.Option>
            <Select.Option value={1}>1 — At least once</Select.Option>
            <Select.Option value={2}>2 — Exactly once</Select.Option>
          </Select>
        </Form.Item>

        <Form.Item name="retain" label="Retain" valuePropName="checked">
          <Switch />
        </Form.Item>

        <Space size="middle">
          <Button
            icon={<SaveOutlined />}
            onClick={handleSave}
            loading={loading}
          >
            Save Config
          </Button>
          {isPublishing ? (
            <Button
              danger
              type="primary"
              icon={<StopOutlined />}
              onClick={handleStop}
              loading={actionLoading}
              size="large"
            >
              Stop Publishing
            </Button>
          ) : (
            <Button
              type="primary"
              icon={<PlayCircleOutlined />}
              onClick={handleStart}
              loading={actionLoading}
              size="large"
              style={{ backgroundColor: "#52c41a", borderColor: "#52c41a" }}
            >
              Start Publishing
            </Button>
          )}
        </Space>
      </Form>
    </Card>
  );
}
