import { SettingOutlined } from "@ant-design/icons";
import { Badge, Button, Card, Descriptions, Space, Table, Typography } from "antd";
import "./DeviceDetail.css";
import type { ColumnsType } from "antd/es/table";
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import type { DeviceSummary, RegisterValue } from "../../types";
import { useDeviceStore } from "../../stores/deviceStore";
import { EditDeviceModal } from "./EditDeviceModal";
import { MqttPublishConfig } from "./MqttPublishConfig";

const STATUS_CONFIG: Record<string, { status: "success" | "default" | "error"; text: string }> = {
  running: { status: "success", text: "Running" },
  stopped: { status: "default", text: "Stopped" },
  error: { status: "error", text: "Error" },
};

const registerColumns: ColumnsType<RegisterValue> = [
  { title: "Name", dataIndex: "name", key: "name" },
  { title: "Address", dataIndex: "address", key: "address", align: "center" },
  {
    title: "FC",
    dataIndex: "function_code",
    key: "function_code",
    align: "center",
    render: (v: number) => `FC${String(v).padStart(2, "0")}`,
  },
  { title: "Data Type", dataIndex: "data_type", key: "data_type" },
  { title: "Byte Order", dataIndex: "byte_order", key: "byte_order" },
  {
    title: "Scale",
    dataIndex: "scale_factor",
    key: "scale_factor",
    align: "center",
  },
  { title: "Unit", dataIndex: "unit", key: "unit" },
  {
    title: "Value",
    dataIndex: "value",
    key: "value",
    align: "center",
    render: (v: number | null) => (v !== null ? v : "\u2014"),
  },
];

export default function DeviceDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [editModalOpen, setEditModalOpen] = useState(false);
  const { currentDevice, loading, fetchDevice, clearCurrentDevice, updateDevice } =
    useDeviceStore();

  const handleInlineUpdate = async (field: "name" | "description", value: string) => {
    if (!currentDevice || !id) return;
    const trimmed = value.trim();
    if (field === "name" && !trimmed) return;
    if (trimmed === (currentDevice[field] ?? "")) return;
    const result = await updateDevice(id, {
      name: currentDevice.name,
      slave_id: currentDevice.slave_id,
      port: currentDevice.port,
      description: currentDevice.description,
      [field]: trimmed || null,
    });
    if (result) {
      fetchDevice(id);
    }
  };

  useEffect(() => {
    if (id) {
      fetchDevice(id);
    }
    return () => clearCurrentDevice();
  }, [id, fetchDevice, clearCurrentDevice]);

  if (!currentDevice && !loading) {
    return <Typography.Text>Device not found</Typography.Text>;
  }

  const statusConfig =
    STATUS_CONFIG[currentDevice?.status ?? "stopped"] ?? STATUS_CONFIG.stopped;

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <Button onClick={() => navigate("/devices")}>Back to List</Button>
        <Button
          icon={<SettingOutlined />}
          onClick={() => setEditModalOpen(true)}
        >
          Edit Settings
        </Button>
      </Space>

      <Typography.Title
        level={2}
        className="device-detail-title"
        editable={{
          onChange: (value) => handleInlineUpdate("name", value),
          triggerType: ["icon"],
          tooltip: "Rename",
        }}
      >
        {currentDevice?.name}
      </Typography.Title>

      <Card style={{ marginBottom: 16 }}>
        <Descriptions column={2}>
          <Descriptions.Item label="Slave ID">
            {currentDevice?.slave_id}
          </Descriptions.Item>
          <Descriptions.Item label="Template">
            {currentDevice?.template_name}
          </Descriptions.Item>
          <Descriptions.Item label="Port">
            {currentDevice?.port}
          </Descriptions.Item>
          <Descriptions.Item label="Status">
            <Badge status={statusConfig.status} text={statusConfig.text} />
          </Descriptions.Item>
          <Descriptions.Item label="Description" span={2}>
            <Typography.Paragraph
              className="device-detail-desc"
              editable={{
                onChange: (value) => handleInlineUpdate("description", value),
                triggerType: ["icon"],
                tooltip: "Edit description",
              }}
              style={{ marginBottom: 0 }}
            >
              {currentDevice?.description ?? ""}
            </Typography.Paragraph>
          </Descriptions.Item>
        </Descriptions>
      </Card>

      <Card title="Register Map">
        <Table
          columns={registerColumns}
          dataSource={currentDevice?.registers ?? []}
          rowKey="name"
          loading={loading}
          pagination={false}
          size="small"
        />
      </Card>

      {id && <MqttPublishConfig deviceId={id} />}

      <EditDeviceModal
        open={editModalOpen}
        device={currentDevice as DeviceSummary | null}
        onClose={() => setEditModalOpen(false)}
        onSuccess={() => { if (id) fetchDevice(id); }}
      />
    </div>
  );
}
