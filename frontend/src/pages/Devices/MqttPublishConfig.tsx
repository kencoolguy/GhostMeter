import {
  DeleteOutlined,
  EditOutlined,
  PlayCircleOutlined,
  PlusOutlined,
  StopOutlined,
} from "@ant-design/icons";
import {
  Alert,
  Badge,
  Button,
  Card,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Radio,
  Select,
  Space,
  Switch,
  Table,
  Typography,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { useCallback, useEffect, useRef, useState } from "react";
import { mqttApi } from "../../services/mqttApi";
import type {
  MqttBroker,
  MqttPublishConfig as MqttConfig,
  MqttPublishConfigWrite,
} from "../../types/mqtt";

interface MqttPublishConfigProps {
  deviceId: string;
  onPublishStateChange?: (publishing: boolean) => void;
}

const CONFIG_DEFAULTS: MqttPublishConfigWrite = {
  topic_template: "telemetry/{device_name}",
  payload_mode: "batch",
  publish_interval_seconds: 5,
  qos: 0,
  retain: false,
};

export function MqttPublishConfig({ deviceId, onPublishStateChange }: MqttPublishConfigProps) {
  const [form] = Form.useForm<MqttPublishConfigWrite>();
  const [configs, setConfigs] = useState<MqttConfig[]>([]);
  const [brokers, setBrokers] = useState<MqttBroker[]>([]);
  const [loading, setLoading] = useState(false);
  const [actionBrokerId, setActionBrokerId] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [modalBroker, setModalBroker] = useState<{ id: string; name: string } | null>(null);
  const [saving, setSaving] = useState(false);

  // Keep the latest callback without retriggering the load effect.
  const onPublishStateChangeRef = useRef(onPublishStateChange);
  useEffect(() => {
    onPublishStateChangeRef.current = onPublishStateChange;
  }, [onPublishStateChange]);

  const applyConfigs = useCallback((next: MqttConfig[]) => {
    setConfigs(next);
    onPublishStateChangeRef.current?.(next.some((c) => c.enabled));
  }, []);

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [configResp, brokerResp] = await Promise.all([
        mqttApi.getDeviceConfigs(deviceId),
        mqttApi.listBrokers(),
      ]);
      applyConfigs(configResp.data ?? []);
      setBrokers(brokerResp.data ?? []);
    } catch {
      // Errors surfaced by the api interceptor
    } finally {
      setLoading(false);
    }
  }, [deviceId, applyConfigs]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const unconfiguredBrokers = brokers.filter(
    (b) => !configs.some((c) => c.broker_id === b.id),
  );

  const openAdd = (broker: MqttBroker) => {
    setModalBroker({ id: broker.id, name: broker.name });
    form.setFieldsValue(CONFIG_DEFAULTS);
    setModalOpen(true);
  };

  const openEdit = (config: MqttConfig) => {
    setModalBroker({ id: config.broker_id, name: config.broker_name });
    form.setFieldsValue({
      topic_template: config.topic_template,
      payload_mode: config.payload_mode,
      publish_interval_seconds: config.publish_interval_seconds,
      qos: config.qos,
      retain: config.retain,
    });
    setModalOpen(true);
  };

  const handleSave = async () => {
    if (!modalBroker) return;
    setSaving(true);
    try {
      const values = await form.validateFields();
      await mqttApi.updateDeviceConfig(deviceId, modalBroker.id, values);
      message.success("MQTT config saved");
      setModalOpen(false);
      await loadAll();
    } catch {
      // Errors surfaced by the api interceptor
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (config: MqttConfig) => {
    try {
      await mqttApi.deleteDeviceConfig(deviceId, config.broker_id);
      message.success("MQTT config deleted");
      await loadAll();
    } catch {
      // Errors surfaced by the api interceptor
    }
  };

  const handleStart = async (config: MqttConfig) => {
    setActionBrokerId(config.broker_id);
    try {
      await mqttApi.startPublishing(deviceId, config.broker_id);
      message.success(`Publishing to ${config.broker_name} started`);
      await loadAll();
    } catch {
      // Errors surfaced by the api interceptor
    } finally {
      setActionBrokerId(null);
    }
  };

  const handleStop = async (config: MqttConfig) => {
    setActionBrokerId(config.broker_id);
    try {
      await mqttApi.stopPublishing(deviceId, config.broker_id);
      message.success(`Publishing to ${config.broker_name} stopped`);
      await loadAll();
    } catch {
      // Errors surfaced by the api interceptor
    } finally {
      setActionBrokerId(null);
    }
  };

  const publishingCount = configs.filter((c) => c.enabled).length;

  const columns: ColumnsType<MqttConfig> = [
    {
      title: "Broker",
      dataIndex: "broker_name",
      key: "broker_name",
      render: (name: string, c) => (
        <Space>
          <Badge status={c.enabled ? "processing" : "default"} />
          <span>{name}</span>
        </Space>
      ),
    },
    { title: "Topic", dataIndex: "topic_template", key: "topic_template" },
    {
      title: "Mode",
      dataIndex: "payload_mode",
      key: "payload_mode",
      render: (mode: string) => (mode === "batch" ? "Batch" : "Per Register"),
    },
    {
      title: "Interval",
      dataIndex: "publish_interval_seconds",
      key: "interval",
      render: (s: number) => `${s}s`,
    },
    { title: "QoS", dataIndex: "qos", key: "qos" },
    {
      title: "Actions",
      key: "actions",
      render: (_, config) => (
        <Space>
          {config.enabled ? (
            <Button
              size="small"
              danger
              icon={<StopOutlined />}
              onClick={() => handleStop(config)}
              loading={actionBrokerId === config.broker_id}
            >
              Stop
            </Button>
          ) : (
            <Button
              size="small"
              type="primary"
              icon={<PlayCircleOutlined />}
              onClick={() => handleStart(config)}
              loading={actionBrokerId === config.broker_id}
              style={{ backgroundColor: "#52c41a", borderColor: "#52c41a" }}
            >
              Start
            </Button>
          )}
          <Button
            size="small"
            icon={<EditOutlined />}
            onClick={() => openEdit(config)}
            disabled={config.enabled}
          >
            Edit
          </Button>
          <Popconfirm
            title={`Remove config for "${config.broker_name}"?`}
            onConfirm={() => handleDelete(config)}
          >
            <Button size="small" danger icon={<DeleteOutlined />} disabled={config.enabled} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <Card
      title={
        <Space>
          <span>MQTT Publishing</span>
          <Badge
            status={publishingCount > 0 ? "processing" : "default"}
            text={
              publishingCount > 0
                ? `Publishing to ${publishingCount} broker${publishingCount > 1 ? "s" : ""}`
                : "Stopped"
            }
          />
        </Space>
      }
      style={{ marginTop: 16 }}
      extra={
        unconfiguredBrokers.length > 0 && (
          <Select
            placeholder={
              <Space>
                <PlusOutlined />
                <span>Add broker config</span>
              </Space>
            }
            value={null}
            style={{ width: 200 }}
            onSelect={(brokerId) => {
              const broker = unconfiguredBrokers.find((b) => b.id === brokerId);
              if (broker) openAdd(broker);
            }}
            options={unconfiguredBrokers.map((b) => ({
              value: b.id,
              label: b.name,
            }))}
          />
        )
      }
    >
      {brokers.length === 0 && !loading ? (
        <Alert
          message="No MQTT brokers configured"
          description="Add a broker in Settings → MQTT Brokers first."
          type="info"
          showIcon
        />
      ) : (
        <Table
          columns={columns}
          dataSource={configs}
          rowKey="broker_id"
          loading={loading}
          pagination={false}
          size="small"
          locale={{ emptyText: "No publish configs — add one via \"Add broker config\"" }}
        />
      )}

      <Modal
        title={`MQTT Config — ${modalBroker?.name ?? ""}`}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        confirmLoading={saving}
        onOk={handleSave}
        okText="Save"
      >
        <Form form={form} layout="vertical" initialValues={CONFIG_DEFAULTS}>
          <Form.Item
            name="topic_template"
            label="Topic Template"
            rules={[{ required: true, message: "Required" }]}
          >
            <Input placeholder="telemetry/{device_name}" />
          </Form.Item>
          <Typography.Text
            type="secondary"
            style={{ display: "block", marginTop: -20, marginBottom: 16, fontSize: 12 }}
          >
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
        </Form>
      </Modal>
    </Card>
  );
}
