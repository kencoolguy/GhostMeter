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
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const {
    devices,
    loading,
    fetchDevices,
    deleteDevice,
    startDevice,
    stopDevice,
    batchStartDevices,
    batchStopDevices,
    batchDeleteDevices,
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

  // --- Batch operations ---

  const handleBatchStart = async (deviceIds: string[]) => {
    const success = await batchStartDevices(deviceIds);
    if (success) {
      setSelectedRowKeys([]);
      await fetchDevices();
    }
  };

  const handleBatchStop = async (deviceIds: string[]) => {
    const success = await batchStopDevices(deviceIds);
    if (success) {
      setSelectedRowKeys([]);
      await fetchDevices();
    }
  };

  const handleBatchDelete = async (deviceIds: string[]) => {
    const success = await batchDeleteDevices(deviceIds);
    if (success) {
      setSelectedRowKeys([]);
      await fetchDevices();
    }
  };

  const selectedIds = selectedRowKeys as string[];
  const hasSelection = selectedIds.length > 0;

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
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 16,
          flexWrap: "wrap",
          gap: 8,
        }}
      >
        <Space>
          <Button
            icon={<PlayCircleOutlined />}
            onClick={() => handleBatchStart([])}
            disabled={loading}
          >
            Start All
          </Button>
          <Button
            icon={<PauseCircleOutlined />}
            onClick={() => handleBatchStop([])}
            disabled={loading}
          >
            Stop All
          </Button>
          {hasSelection && (
            <>
              <Button
                type="primary"
                icon={<PlayCircleOutlined />}
                onClick={() => handleBatchStart(selectedIds)}
                disabled={loading}
              >
                Start Selected ({selectedIds.length})
              </Button>
              <Button
                icon={<PauseCircleOutlined />}
                onClick={() => handleBatchStop(selectedIds)}
                disabled={loading}
              >
                Stop Selected ({selectedIds.length})
              </Button>
              <Popconfirm
                title={`Delete ${selectedIds.length} device(s)? Running devices will be skipped.`}
                onConfirm={() => handleBatchDelete(selectedIds)}
              >
                <Button danger disabled={loading}>
                  Delete Selected ({selectedIds.length})
                </Button>
              </Popconfirm>
            </>
          )}
        </Space>
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
        rowSelection={{
          selectedRowKeys,
          onChange: setSelectedRowKeys,
        }}
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
