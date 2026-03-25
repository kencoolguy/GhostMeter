import { Button, Modal, Space, Table, Tag, Tooltip } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useEffect, useState } from "react";
import { useProfileStore } from "../../stores/profileStore";
import type { RegisterDefinition, SimulationProfile } from "../../types";
import { ProfileFormModal } from "./ProfileFormModal";

interface ProfilesTabProps {
  templateId: string;
  registers: Omit<RegisterDefinition, "id">[];
  readOnly?: boolean;
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
      width: 240,
      render: (_: unknown, record) => (
        <Space>
          <Button size="small" onClick={() => handleEdit(record)}>
            Edit
          </Button>
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
        <div style={{ marginBottom: 16 }}>
          <Button type="primary" onClick={handleCreate}>
            New Profile
          </Button>
        </div>
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
