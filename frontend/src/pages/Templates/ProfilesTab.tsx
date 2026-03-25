import {
  DownloadOutlined,
  ExportOutlined,
  ImportOutlined,
} from "@ant-design/icons";
import { Button, Modal, Space, Table, Tag, Tooltip, Upload, message } from "antd";
import type { ColumnsType } from "antd/es/table";
import type { UploadFile } from "antd/es/upload";
import { useEffect, useState } from "react";
import { profileApi } from "../../services/profileApi";
import { useProfileStore } from "../../stores/profileStore";
import type { RegisterDefinition, SimulationProfile } from "../../types";
import { ProfileFormModal } from "./ProfileFormModal";

interface ProfilesTabProps {
  templateId: string;
  registers: Omit<RegisterDefinition, "id">[];
  readOnly?: boolean;
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function ProfilesTab({
  templateId,
  registers,
  readOnly,
}: ProfilesTabProps) {
  const { profiles, loading, fetchProfiles, updateProfile, deleteProfile } =
    useProfileStore();
  const [modalOpen, setModalOpen] = useState(false);
  const [editingProfile, setEditingProfile] =
    useState<SimulationProfile | null>(null);

  useEffect(() => {
    fetchProfiles(templateId);
  }, [templateId, fetchProfiles]);

  const handleEdit = (profile: SimulationProfile) => {
    setEditingProfile(profile);
    setModalOpen(true);
  };

  const handleCreate = () => {
    setEditingProfile(null);
    setModalOpen(true);
  };

  const handleDelete = (profile: SimulationProfile) => {
    Modal.confirm({
      title: "Delete Profile",
      content: `Are you sure you want to delete "${profile.name}"?`,
      okText: "Delete",
      okType: "danger",
      onOk: async () => {
        const success = await deleteProfile(profile.id);
        if (success) {
          await fetchProfiles(templateId);
        }
      },
    });
  };

  const handleSetDefault = async (profile: SimulationProfile) => {
    const success = await updateProfile(profile.id, { is_default: true });
    if (success) {
      await fetchProfiles(templateId);
    }
  };

  const handleExport = async (profile: SimulationProfile) => {
    try {
      const blob = await profileApi.exportProfile(profile.id);
      const filename = `${profile.name.replace(/\s+/g, "_").toLowerCase()}.json`;
      downloadBlob(blob, filename);
    } catch {
      message.error("Failed to export profile");
    }
  };

  const handleDownloadBlank = async () => {
    try {
      const blob = await profileApi.downloadBlankTemplate(templateId);
      downloadBlob(blob, "blank_profile.json");
    } catch {
      message.error("Failed to download blank template");
    }
  };

  const handleImport = async (file: UploadFile) => {
    try {
      await profileApi.importProfile(templateId, file as unknown as File);
      message.success("Profile imported successfully");
      await fetchProfiles(templateId);
    } catch {
      // Error interceptor already shows message
    }
    return false; // Prevent default upload behavior
  };

  const columns: ColumnsType<SimulationProfile> = [
    {
      title: "Name",
      dataIndex: "name",
      key: "name",
      render: (name: string, record) => (
        <Space>
          {name}
          {record.is_builtin && <Tag color="blue">Built-in</Tag>}
          {record.is_default && <Tag color="green">Default</Tag>}
        </Space>
      ),
    },
    {
      title: "Description",
      dataIndex: "description",
      key: "description",
      ellipsis: true,
    },
    {
      title: "Configs",
      key: "config_count",
      width: 80,
      render: (_: unknown, record) => record.configs.length,
    },
    {
      title: "Actions",
      key: "actions",
      width: 300,
      render: (_: unknown, record) => (
        <Space>
          <Button size="small" onClick={() => handleEdit(record)}>
            Edit
          </Button>
          <Tooltip title="Export as JSON">
            <Button
              size="small"
              icon={<ExportOutlined />}
              onClick={() => handleExport(record)}
            />
          </Tooltip>
          {!record.is_default && (
            <Button size="small" onClick={() => handleSetDefault(record)}>
              Set Default
            </Button>
          )}
          {record.is_builtin ? (
            <Tooltip title="Built-in profiles cannot be deleted">
              <Button size="small" danger disabled>
                Delete
              </Button>
            </Tooltip>
          ) : (
            <Button size="small" danger onClick={() => handleDelete(record)}>
              Delete
            </Button>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div>
      {!readOnly && (
        <Space style={{ marginBottom: 16 }}>
          <Button type="primary" onClick={handleCreate}>
            New Profile
          </Button>
          <Upload
            accept=".json"
            showUploadList={false}
            beforeUpload={handleImport}
          >
            <Button icon={<ImportOutlined />}>Import Profile</Button>
          </Upload>
          <Button icon={<DownloadOutlined />} onClick={handleDownloadBlank}>
            Download Blank Template
          </Button>
        </Space>
      )}
      <Table
        columns={columns}
        dataSource={profiles}
        rowKey="id"
        loading={loading}
        pagination={false}
        size="small"
      />
      <ProfileFormModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        templateId={templateId}
        registers={registers}
        profile={editingProfile}
      />
    </div>
  );
}
