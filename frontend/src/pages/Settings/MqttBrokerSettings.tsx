import { ApiOutlined, SaveOutlined } from "@ant-design/icons";
import {
  Button,
  Card,
  Form,
  Input,
  InputNumber,
  Space,
  Switch,
  message,
} from "antd";
import { useEffect, useState } from "react";
import { mqttApi } from "../../services/mqttApi";
import type { MqttBrokerSettings as BrokerSettings } from "../../types/mqtt";

export function MqttBrokerSettings() {
  const [form] = Form.useForm<BrokerSettings>();
  const [loading, setLoading] = useState(false);
  const [testing, setTesting] = useState(false);

  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    try {
      const resp = await mqttApi.getBrokerSettings();
      if (resp.data) {
        form.setFieldsValue(resp.data);
      }
    } catch {
      // Use defaults
    }
  };

  const handleSave = async () => {
    setLoading(true);
    try {
      const values = await form.validateFields();
      await mqttApi.updateBrokerSettings(values);
      message.success("MQTT broker settings saved");
    } catch {
      message.error("Failed to save settings");
    } finally {
      setLoading(false);
    }
  };

  const handleTest = async () => {
    setTesting(true);
    try {
      const values = await form.validateFields();
      const resp = await mqttApi.testConnection(values);
      if (resp.data?.success) {
        message.success("Connection successful");
      } else {
        message.error(`Connection failed: ${resp.data?.message}`);
      }
    } catch {
      message.error("Connection test failed");
    } finally {
      setTesting(false);
    }
  };

  return (
    <Card title="MQTT Broker" style={{ maxWidth: 600, marginTop: 16 }}>
      <Form form={form} layout="vertical">
        <Form.Item
          name="host"
          label="Host"
          rules={[{ required: true, message: "Required" }]}
        >
          <Input placeholder="localhost" />
        </Form.Item>
        <Form.Item
          name="port"
          label="Port"
          rules={[{ required: true, message: "Required" }]}
        >
          <InputNumber min={1} max={65535} style={{ width: "100%" }} />
        </Form.Item>
        <Form.Item name="username" label="Username">
          <Input placeholder="(optional)" />
        </Form.Item>
        <Form.Item name="password" label="Password">
          <Input.Password placeholder="(optional)" />
        </Form.Item>
        <Form.Item name="client_id" label="Client ID">
          <Input placeholder="ghostmeter" />
        </Form.Item>
        <Form.Item name="use_tls" label="Use TLS" valuePropName="checked">
          <Switch />
        </Form.Item>
        <Space>
          <Button
            type="primary"
            icon={<SaveOutlined />}
            onClick={handleSave}
            loading={loading}
          >
            Save
          </Button>
          <Button
            icon={<ApiOutlined />}
            onClick={handleTest}
            loading={testing}
          >
            Test Connection
          </Button>
        </Space>
      </Form>
    </Card>
  );
}
