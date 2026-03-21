import {
  DeleteOutlined,
  EditOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined,
  PlusOutlined,
} from "@ant-design/icons";
import { Badge, Button, Popconfirm, Space, Table, Tooltip } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import type { DeviceSummary } from "../../types";
import { useDeviceStore } from "../../stores/deviceStore";
import { CreateDeviceModal } from "./CreateDeviceModal";
import { EditDeviceModal } from "./EditDeviceModal";

const STATUS_CONFIG: Record<string, { status: "success" | "default" | "error"; text: string }> = {
  running: { status: "success", text: "Running" },
  stopped: { status: "default", text: "Stopped" },
  error: { status: "error", text: "Error" },
};

export function DeviceList() {
  const navigate = useNavigate();
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [editingDevice, setEditingDevice] = useState<DeviceSummary | null>(null);
  const {
    devices,
    loading,
    fetchDevices,
    deleteDevice,
    startDevice,
    stopDevice,
  } = useDeviceStore();

  useEffect(() => {
    fetchDevices();
  }, [fetchDevices]);

  const handleToggle = async (device: DeviceSummary) => {
    let success: boolean;
    if (device.status === "running") {
      success = await stopDevice(device.id);
    } else {
      success = await startDevice(device.id);
    }
    if (success) {
      await fetchDevices();
    }
  };

  const handleEdit = (device: DeviceSummary) => {
    setEditingDevice(device);
    setEditModalOpen(true);
  };

  const handleDelete = async (id: string) => {
    const success = await deleteDevice(id);
    if (success) {
      await fetchDevices();
    }
  };

  const columns: ColumnsType<DeviceSummary> = [
    {
      title: "Name",
      dataIndex: "name",
      key: "name",
      render: (name: string, record) => (
        <a onClick={() => navigate(`/devices/${record.id}`)}>{name}</a>
      ),
    },
    {
      title: "Slave ID",
      dataIndex: "slave_id",
      key: "slave_id",
      align: "center",
      width: 100,
    },
    {
      title: "Template",
      dataIndex: "template_name",
      key: "template_name",
    },
    {
      title: "Port",
      dataIndex: "port",
      key: "port",
      align: "center",
      width: 80,
    },
    {
      title: "Status",
      dataIndex: "status",
      key: "status",
      width: 120,
      render: (status: string) => {
        const config = STATUS_CONFIG[status] ?? STATUS_CONFIG.stopped;
        return <Badge status={config.status} text={config.text} />;
      },
    },
    {
      title: "Actions",
      key: "actions",
      width: 120,
      render: (_, record) => (
        <Space size="small">
          <Tooltip title={record.status === "running" ? "Stop" : "Start"}>
            <Button
              type="text"
              size="small"
              icon={
                record.status === "running" ? (
                  <PauseCircleOutlined />
                ) : (
                  <PlayCircleOutlined />
                )
              }
              onClick={() => handleToggle(record)}
              disabled={record.status === "error"}
            />
          </Tooltip>
          <Tooltip title="Edit">
            <Button
              type="text"
              size="small"
              icon={<EditOutlined />}
              onClick={() => handleEdit(record)}
            />
          </Tooltip>
          {record.status !== "running" && (
            <Popconfirm
              title="Delete this device?"
              onConfirm={() => handleDelete(record.id)}
            >
              <Tooltip title="Delete">
                <Button
                  type="text"
                  size="small"
                  danger
                  icon={<DeleteOutlined />}
                />
              </Tooltip>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div
        style={{
          display: "flex",
          justifyContent: "flex-end",
          marginBottom: 16,
        }}
      >
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => setCreateModalOpen(true)}
        >
          New Device
        </Button>
      </div>
      <Table
        columns={columns}
        dataSource={devices}
        rowKey="id"
        loading={loading}
        pagination={false}
      />
      <CreateDeviceModal
        open={createModalOpen}
        onClose={() => setCreateModalOpen(false)}
      />
      <EditDeviceModal
        open={editModalOpen}
        device={editingDevice}
        onClose={() => {
          setEditModalOpen(false);
          setEditingDevice(null);
        }}
        onSuccess={() => fetchDevices()}
      />
    </div>
  );
}
