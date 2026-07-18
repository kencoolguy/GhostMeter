import { ApiOutlined, DeleteOutlined, EditOutlined, PlusOutlined } from "@ant-design/icons";
import {
  Badge,
  Button,
  Card,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Space,
  Switch,
  Table,
  Tag,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { useCallback, useEffect, useState } from "react";
import { mqttApi } from "../../services/mqttApi";
import type { MqttBroker, MqttBrokerWrite } from "../../types/mqtt";

export function MqttBrokerSettings() {
  const [brokers, setBrokers] = useState<MqttBroker[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<MqttBroker | null>(null);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [form] = Form.useForm<MqttBrokerWrite>();

  const loadBrokers = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await mqttApi.listBrokers();
      setBrokers(resp.data ?? []);
    } catch {
      message.error("Failed to load MQTT brokers");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadBrokers();
  }, [loadBrokers]);

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    setModalOpen(true);
  };

  const openEdit = (broker: MqttBroker) => {
    setEditing(broker);
    form.setFieldsValue(broker);
    setModalOpen(true);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const values = await form.validateFields();
      if (editing) {
        await mqttApi.updateBroker(editing.id, values);
        message.success("MQTT broker updated");
      } else {
        await mqttApi.createBroker(values);
        message.success("MQTT broker created");
      }
      setModalOpen(false);
      await loadBrokers();
    } catch {
      // Backend detail (e.g. duplicate name) is surfaced by the api interceptor
    } finally {
      setSaving(false);
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

  const handleDelete = async (broker: MqttBroker) => {
    try {
      await mqttApi.deleteBroker(broker.id);
      message.success("MQTT broker deleted");
      await loadBrokers();
    } catch {
      // Backend detail (e.g. broker in use) is surfaced by the api interceptor
    }
  };

  const columns: ColumnsType<MqttBroker> = [
    { title: "Name", dataIndex: "name", key: "name" },
    {
      title: "Address",
      key: "address",
      render: (_, b) => `${b.host}:${b.port}`,
    },
    { title: "Client ID", dataIndex: "client_id", key: "client_id" },
    {
      title: "TLS",
      dataIndex: "use_tls",
      key: "use_tls",
      render: (useTls: boolean) => (useTls ? <Tag color="blue">TLS</Tag> : "—"),
    },
    {
      title: "Status",
      dataIndex: "connected",
      key: "connected",
      render: (connected: boolean) => (
        <Badge
          status={connected ? "success" : "default"}
          text={connected ? "Connected" : "Disconnected"}
        />
      ),
    },
    {
      title: "Actions",
      key: "actions",
      render: (_, broker) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(broker)}>
            Edit
          </Button>
          <Popconfirm
            title={`Delete broker "${broker.name}"?`}
            description="Device publish configs must be removed first."
            onConfirm={() => handleDelete(broker)}
          >
            <Button size="small" danger icon={<DeleteOutlined />}>
              Delete
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <Card
      title="MQTT Brokers"
      style={{ marginTop: 16 }}
      extra={
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
          Add Broker
        </Button>
      }
    >
      <Table
        columns={columns}
        dataSource={brokers}
        rowKey="id"
        loading={loading}
        pagination={false}
        size="small"
        locale={{ emptyText: "No MQTT brokers configured" }}
      />

      <Modal
        title={editing ? `Edit Broker: ${editing.name}` : "Add MQTT Broker"}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        footer={[
          <Button key="test" icon={<ApiOutlined />} onClick={handleTest} loading={testing}>
            Test Connection
          </Button>,
          <Button key="cancel" onClick={() => setModalOpen(false)}>
            Cancel
          </Button>,
          <Button key="save" type="primary" onClick={handleSave} loading={saving}>
            Save
          </Button>,
        ]}
      >
        <Form
          form={form}
          layout="vertical"
          initialValues={{
            host: "localhost",
            port: 1883,
            username: "",
            password: "",
            client_id: "ghostmeter",
            use_tls: false,
          }}
        >
          <Form.Item
            name="name"
            label="Name"
            rules={[{ required: true, message: "Required" }]}
          >
            <Input placeholder="e.g. emqx-production" />
          </Form.Item>
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
        </Form>
      </Modal>
    </Card>
  );
}
