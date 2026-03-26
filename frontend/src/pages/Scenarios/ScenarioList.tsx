import {
  DeleteOutlined,
  DownloadOutlined,
  EditOutlined,
  PlusOutlined,
  UploadOutlined,
} from "@ant-design/icons";
import { Button, Popconfirm, Space, Table, Tag, Tooltip, Upload, message } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { scenarioApi } from "../../services/scenarioApi";
import { useScenarioStore } from "../../stores/scenarioStore";
import type { ScenarioSummary } from "../../types/scenario";

export function ScenarioList() {
  const navigate = useNavigate();
  const { scenarios, loading, fetchScenarios, deleteScenario } = useScenarioStore();

  useEffect(() => {
    fetchScenarios();
  }, [fetchScenarios]);

  const handleDelete = async (id: string) => {
    const success = await deleteScenario(id);
    if (success) await fetchScenarios();
  };

  const handleExport = async (id: string, name: string) => {
    try {
      const resp = await scenarioApi.export(id);
      const blob = new Blob([JSON.stringify(resp.data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${name.replace(/\s+/g, "_").toLowerCase()}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      message.error("Failed to export scenario");
    }
  };

  const handleImport = async (file: File) => {
    try {
      const text = await file.text();
      const data = JSON.parse(text);
      await scenarioApi.import(data);
      message.success("Scenario imported");
      await fetchScenarios();
    } catch {
      message.error("Failed to import scenario");
    }
    return false; // Prevent antd default upload
  };

  const formatDuration = (seconds: number) => {
    if (seconds < 60) return `${seconds}s`;
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return s > 0 ? `${m}m ${s}s` : `${m}m`;
  };

  const columns: ColumnsType<ScenarioSummary> = [
    {
      title: "Name",
      dataIndex: "name",
      key: "name",
      render: (name: string, record) => (
        <Space>
          <a onClick={() => navigate(`/scenarios/${record.id}`)}>{name}</a>
          {record.is_builtin && <Tag color="blue">Built-in</Tag>}
        </Space>
      ),
    },
    { title: "Template", dataIndex: "template_name", key: "template_name" },
    {
      title: "Duration",
      dataIndex: "total_duration_seconds",
      key: "duration",
      width: 100,
      render: (v: number) => formatDuration(v),
    },
    {
      title: "Actions",
      key: "actions",
      width: 140,
      render: (_, record) => (
        <Space size="small">
          <Tooltip title="Edit">
            <Button
              type="text"
              size="small"
              icon={<EditOutlined />}
              onClick={() => navigate(`/scenarios/${record.id}`)}
            />
          </Tooltip>
          <Tooltip title="Export">
            <Button
              type="text"
              size="small"
              icon={<DownloadOutlined />}
              onClick={() => handleExport(record.id, record.name)}
            />
          </Tooltip>
          {!record.is_builtin && (
            <Popconfirm title="Delete this scenario?" onConfirm={() => handleDelete(record.id)}>
              <Tooltip title="Delete">
                <Button type="text" size="small" danger icon={<DeleteOutlined />} />
              </Tooltip>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
        <Space>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate("/scenarios/new")}>
            New Scenario
          </Button>
          <Upload accept=".json" showUploadList={false} beforeUpload={handleImport}>
            <Button icon={<UploadOutlined />}>Import</Button>
          </Upload>
        </Space>
      </div>
      <Table
        columns={columns}
        dataSource={scenarios}
        rowKey="id"
        loading={loading}
        pagination={false}
      />
    </div>
  );
}
