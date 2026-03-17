import {
  CopyOutlined,
  DeleteOutlined,
  EditOutlined,
  ExportOutlined,
  PlusOutlined,
} from "@ant-design/icons";
import { Button, Popconfirm, Space, Table, Tag, Tooltip } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import type { TemplateSummary } from "../../types";
import { useTemplateStore } from "../../stores/templateStore";
import { handleExport, ImportExportButtons } from "./ImportExportButtons";

export function TemplateList() {
  const navigate = useNavigate();
  const { templates, loading, fetchTemplates, deleteTemplate, cloneTemplate } =
    useTemplateStore();

  useEffect(() => {
    fetchTemplates();
  }, [fetchTemplates]);

  const handleDelete = async (id: string) => {
    const success = await deleteTemplate(id);
    if (success) {
      await fetchTemplates();
    }
  };

  const handleClone = async (id: string) => {
    const cloned = await cloneTemplate(id);
    if (cloned) {
      await fetchTemplates();
    }
  };

  const columns: ColumnsType<TemplateSummary> = [
    {
      title: "Name",
      dataIndex: "name",
      key: "name",
      render: (name: string, record) => (
        <Space>
          {name}
          {record.is_builtin && <Tag color="blue">Built-in</Tag>}
        </Space>
      ),
    },
    {
      title: "Protocol",
      dataIndex: "protocol",
      key: "protocol",
    },
    {
      title: "Registers",
      dataIndex: "register_count",
      key: "register_count",
      align: "center",
    },
    {
      title: "Created",
      dataIndex: "created_at",
      key: "created_at",
      render: (val: string) => new Date(val).toLocaleDateString(),
    },
    {
      title: "Actions",
      key: "actions",
      render: (_, record) => (
        <Space size="small">
          {!record.is_builtin && (
            <Tooltip title="Edit">
              <Button
                type="text"
                size="small"
                icon={<EditOutlined />}
                onClick={() => navigate(`/templates/${record.id}`)}
              />
            </Tooltip>
          )}
          <Tooltip title="Clone">
            <Button
              type="text"
              size="small"
              icon={<CopyOutlined />}
              onClick={() => handleClone(record.id)}
            />
          </Tooltip>
          <Tooltip title="Export">
            <Button
              type="text"
              size="small"
              icon={<ExportOutlined />}
              onClick={() => handleExport(record.id, record.name)}
            />
          </Tooltip>
          {!record.is_builtin && (
            <Popconfirm
              title="Delete this template?"
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
          marginBottom: 16,
        }}
      >
        <div />
        <Space>
          <ImportExportButtons />
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => navigate("/templates/new")}
          >
            New Template
          </Button>
        </Space>
      </div>
      <Table
        columns={columns}
        dataSource={templates}
        rowKey="id"
        loading={loading}
        pagination={false}
      />
    </div>
  );
}
