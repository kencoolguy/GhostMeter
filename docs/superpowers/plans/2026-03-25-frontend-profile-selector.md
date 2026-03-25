# Frontend Profile Selector Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add frontend UI for simulation profile management (CRUD in template detail) and profile selection in device creation modal.

**Architecture:** New profile types, API client, and Zustand store follow the exact patterns established by device/template modules. ProfilesTab renders inside TemplateForm as a second tab. ProfileFormModal reuses DataModeTab's config table pattern. CreateDeviceModal gets a dependent profile dropdown that fetches on template change.

**Tech Stack:** React 18, TypeScript, Ant Design 5, Zustand, Axios

**Spec:** `docs/superpowers/specs/2026-03-25-frontend-profile-selector-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `frontend/src/types/profile.ts` | Create | Profile TypeScript interfaces |
| `frontend/src/types/device.ts` | Modify | Add `profile_id` to CreateDevice/BatchCreateDevice |
| `frontend/src/types/index.ts` | Modify | Re-export profile types |
| `frontend/src/services/profileApi.ts` | Create | API client for `/api/v1/simulation-profiles` |
| `frontend/src/stores/profileStore.ts` | Create | Zustand store for profile state |
| `frontend/src/pages/Templates/ProfilesTab.tsx` | Create | Profile list table with CRUD actions |
| `frontend/src/pages/Templates/ProfileFormModal.tsx` | Create | Create/edit profile modal with config table |
| `frontend/src/pages/Templates/TemplateForm.tsx` | Modify | Add Tabs wrapper with Register Map + Profiles |
| `frontend/src/pages/Devices/CreateDeviceModal.tsx` | Modify | Add profile dropdown after template select |

---

## Chunk 1: Types, API Client, Store

### Task 1: Create profile TypeScript types

**Files:**
- Create: `frontend/src/types/profile.ts`
- Modify: `frontend/src/types/index.ts`

- [ ] **Step 1: Create profile types file**

```typescript
// frontend/src/types/profile.ts

export type DataMode = "static" | "random" | "daily_curve" | "computed" | "accumulator";

export interface ProfileConfigEntry {
  register_name: string;
  data_mode: DataMode;
  mode_params: Record<string, unknown>;
  is_enabled: boolean;
  update_interval_ms: number;
}

export interface SimulationProfile {
  id: string;
  template_id: string;
  name: string;
  description: string | null;
  is_builtin: boolean;
  is_default: boolean;
  configs: ProfileConfigEntry[];
  created_at: string;
  updated_at: string;
}

export interface CreateProfile {
  template_id: string;
  name: string;
  description?: string | null;
  is_default?: boolean;
  configs: ProfileConfigEntry[];
}

export interface UpdateProfile {
  name?: string;
  description?: string | null;
  is_default?: boolean;
  configs?: ProfileConfigEntry[];
}
```

- [ ] **Step 2: Add profile exports to types/index.ts**

Add after the mqtt exports block in `frontend/src/types/index.ts`:

```typescript
export type {
  CreateProfile,
  DataMode,
  ProfileConfigEntry,
  SimulationProfile,
  UpdateProfile,
} from "./profile";
```

- [ ] **Step 3: Add profile_id to device types**

In `frontend/src/types/device.ts`, add `profile_id` to both interfaces:

```typescript
// In CreateDevice, after description:
  profile_id?: string | null;

// In BatchCreateDevice, after description:
  profile_id?: string | null;
```

- [ ] **Step 4: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors related to profile types.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/profile.ts frontend/src/types/index.ts frontend/src/types/device.ts
git commit -m "feat: add profile TypeScript types and profile_id to device types"
```

---

### Task 2: Create profile API client

**Files:**
- Create: `frontend/src/services/profileApi.ts`

- [ ] **Step 1: Create profileApi.ts**

Follow the exact pattern from `templateApi.ts`:

```typescript
// frontend/src/services/profileApi.ts

import { api } from "./api";
import type {
  ApiResponse,
  CreateProfile,
  SimulationProfile,
  UpdateProfile,
} from "../types";

export const profileApi = {
  list: (templateId: string) =>
    api
      .get<ApiResponse<SimulationProfile[]>>("/simulation-profiles", {
        params: { template_id: templateId },
      })
      .then((r) => r.data),

  get: (id: string) =>
    api
      .get<ApiResponse<SimulationProfile>>(`/simulation-profiles/${id}`)
      .then((r) => r.data),

  create: (data: CreateProfile) =>
    api
      .post<ApiResponse<SimulationProfile>>("/simulation-profiles", data)
      .then((r) => r.data),

  update: (id: string, data: UpdateProfile) =>
    api
      .put<ApiResponse<SimulationProfile>>(`/simulation-profiles/${id}`, data)
      .then((r) => r.data),

  delete: (id: string) =>
    api
      .delete<ApiResponse<null>>(`/simulation-profiles/${id}`)
      .then((r) => r.data),
};
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/services/profileApi.ts
git commit -m "feat: add profile API client"
```

---

### Task 3: Create profile Zustand store

**Files:**
- Create: `frontend/src/stores/profileStore.ts`

- [ ] **Step 1: Create profileStore.ts**

Follow the exact pattern from `deviceStore.ts`:

```typescript
// frontend/src/stores/profileStore.ts

import { message } from "antd";
import { create } from "zustand";
import { profileApi } from "../services/profileApi";
import type {
  CreateProfile,
  SimulationProfile,
  UpdateProfile,
} from "../types";

interface ProfileState {
  profiles: SimulationProfile[];
  loading: boolean;
  fetchProfiles: (templateId: string) => Promise<void>;
  createProfile: (data: CreateProfile) => Promise<boolean>;
  updateProfile: (id: string, data: UpdateProfile) => Promise<boolean>;
  deleteProfile: (id: string) => Promise<boolean>;
  clearProfiles: () => void;
}

export const useProfileStore = create<ProfileState>((set) => ({
  profiles: [],
  loading: false,

  fetchProfiles: async (templateId: string) => {
    set({ loading: true });
    try {
      const response = await profileApi.list(templateId);
      set({ profiles: response.data ?? [] });
    } catch {
      set({ profiles: [] });
    } finally {
      set({ loading: false });
    }
  },

  createProfile: async (data: CreateProfile) => {
    set({ loading: true });
    try {
      await profileApi.create(data);
      message.success("Profile created successfully");
      return true;
    } catch {
      return false;
    } finally {
      set({ loading: false });
    }
  },

  updateProfile: async (id: string, data: UpdateProfile) => {
    set({ loading: true });
    try {
      await profileApi.update(id, data);
      message.success("Profile updated successfully");
      return true;
    } catch {
      return false;
    } finally {
      set({ loading: false });
    }
  },

  deleteProfile: async (id: string) => {
    set({ loading: true });
    try {
      await profileApi.delete(id);
      message.success("Profile deleted successfully");
      return true;
    } catch {
      return false;
    } finally {
      set({ loading: false });
    }
  },

  clearProfiles: () => set({ profiles: [] }),
}));
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/stores/profileStore.ts
git commit -m "feat: add profile Zustand store"
```

---

## Chunk 2: Profile Management UI (ProfilesTab + ProfileFormModal)

### Task 4: Create ProfileFormModal

**Files:**
- Create: `frontend/src/pages/Templates/ProfileFormModal.tsx`

**Context:** This modal is used for both creating and editing profiles. It has a name/description form at the top and a per-register config table at the bottom (same pattern as `DataModeTab.tsx`). For built-in profiles, the config table is read-only.

- [ ] **Step 1: Create ProfileFormModal.tsx**

```typescript
// frontend/src/pages/Templates/ProfileFormModal.tsx

import {
  Form,
  Input,
  InputNumber,
  Modal,
  Select,
  Switch,
  Table,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { useEffect, useState } from "react";
import { useProfileStore } from "../../stores/profileStore";
import type {
  DataMode,
  ProfileConfigEntry,
  RegisterDefinition,
  SimulationProfile,
} from "../../types";

const DATA_MODE_OPTIONS = [
  { value: "static", label: "Static" },
  { value: "random", label: "Random" },
  { value: "daily_curve", label: "Daily Curve" },
  { value: "computed", label: "Computed" },
  { value: "accumulator", label: "Accumulator" },
];

interface ConfigRow {
  key: string;
  register_name: string;
  data_mode: DataMode;
  mode_params: string;
  is_enabled: boolean;
  update_interval_ms: number;
}

interface ProfileFormModalProps {
  open: boolean;
  onClose: () => void;
  templateId: string;
  registers: Omit<RegisterDefinition, "id">[];
  profile?: SimulationProfile | null;
}

export function ProfileFormModal({
  open,
  onClose,
  templateId,
  registers,
  profile,
}: ProfileFormModalProps) {
  const [form] = Form.useForm();
  const { createProfile, updateProfile, fetchProfiles, loading } =
    useProfileStore();
  const [rows, setRows] = useState<ConfigRow[]>([]);

  const isEdit = Boolean(profile);
  const isBuiltinConfigs = Boolean(profile?.is_builtin);

  useEffect(() => {
    if (!open) return;

    if (profile) {
      form.setFieldsValue({
        name: profile.name,
        description: profile.description,
      });
    } else {
      form.resetFields();
    }

    // Build config rows from template registers
    const configMap = new Map(
      (profile?.configs ?? []).map((c) => [c.register_name, c]),
    );

    const newRows: ConfigRow[] = registers.map((reg) => {
      const existing = configMap.get(reg.name);
      return {
        key: reg.name,
        register_name: reg.name,
        data_mode: (existing?.data_mode as DataMode) ?? "static",
        mode_params: existing
          ? JSON.stringify(existing.mode_params, null, 2)
          : "{}",
        is_enabled: existing?.is_enabled ?? true,
        update_interval_ms: existing?.update_interval_ms ?? 1000,
      };
    });
    setRows(newRows);
  }, [open, profile, registers, form]);

  const updateRow = (key: string, field: keyof ConfigRow, value: unknown) => {
    setRows((prev) =>
      prev.map((r) => (r.key === key ? { ...r, [field]: value } : r)),
    );
  };

  const handleSubmit = async () => {
    const values = await form.validateFields();

    // Parse config rows
    const configs: ProfileConfigEntry[] = [];
    for (const row of rows) {
      let parsedParams: Record<string, unknown>;
      try {
        parsedParams = JSON.parse(row.mode_params);
      } catch {
        message.error(
          `Invalid JSON in params for register "${row.register_name}"`,
        );
        return;
      }
      configs.push({
        register_name: row.register_name,
        data_mode: row.data_mode,
        mode_params: parsedParams,
        is_enabled: row.is_enabled,
        update_interval_ms: row.update_interval_ms,
      });
    }

    let success: boolean;
    if (isEdit && profile) {
      const updateData = isBuiltinConfigs
        ? { name: values.name, description: values.description }
        : { name: values.name, description: values.description, configs };
      success = await updateProfile(profile.id, updateData);
    } else {
      success = await createProfile({
        template_id: templateId,
        name: values.name,
        description: values.description,
        configs,
      });
    }

    if (success) {
      await fetchProfiles(templateId);
      onClose();
    }
  };

  const columns: ColumnsType<ConfigRow> = [
    {
      title: "Register",
      dataIndex: "register_name",
      key: "register_name",
      width: 180,
    },
    {
      title: "Data Mode",
      dataIndex: "data_mode",
      key: "data_mode",
      width: 160,
      render: (value: string, record) => (
        <Select
          value={value}
          options={DATA_MODE_OPTIONS}
          style={{ width: "100%" }}
          onChange={(v) => updateRow(record.key, "data_mode", v)}
          disabled={isBuiltinConfigs}
        />
      ),
    },
    {
      title: "Parameters (JSON)",
      dataIndex: "mode_params",
      key: "mode_params",
      render: (value: string, record) => (
        <Input.TextArea
          value={value}
          rows={2}
          style={{ fontFamily: "monospace", fontSize: 12 }}
          onChange={(e) => updateRow(record.key, "mode_params", e.target.value)}
          disabled={isBuiltinConfigs}
        />
      ),
    },
    {
      title: "Interval (ms)",
      dataIndex: "update_interval_ms",
      key: "update_interval_ms",
      width: 120,
      render: (value: number, record) => (
        <InputNumber
          value={value}
          min={100}
          step={100}
          style={{ width: "100%" }}
          onChange={(v) =>
            updateRow(record.key, "update_interval_ms", v ?? 1000)
          }
          disabled={isBuiltinConfigs}
        />
      ),
    },
    {
      title: "Enabled",
      dataIndex: "is_enabled",
      key: "is_enabled",
      width: 80,
      align: "center" as const,
      render: (value: boolean, record) => (
        <Switch
          checked={value}
          onChange={(v) => updateRow(record.key, "is_enabled", v)}
          disabled={isBuiltinConfigs}
        />
      ),
    },
  ];

  return (
    <Modal
      title={isEdit ? "Edit Profile" : "New Profile"}
      open={open}
      onOk={handleSubmit}
      onCancel={onClose}
      width={900}
      destroyOnClose
      confirmLoading={loading}
    >
      <Form form={form} layout="vertical" style={{ marginBottom: 16 }}>
        <Form.Item
          name="name"
          label="Profile Name"
          rules={[{ required: true, message: "Please enter a name" }]}
        >
          <Input placeholder="e.g. Normal Operation" />
        </Form.Item>
        <Form.Item name="description" label="Description">
          <Input.TextArea rows={2} placeholder="Optional description" />
        </Form.Item>
      </Form>

      <Table
        columns={columns}
        dataSource={rows}
        rowKey="key"
        pagination={false}
        size="small"
        scroll={{ y: 400 }}
      />
    </Modal>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Templates/ProfileFormModal.tsx
git commit -m "feat: add ProfileFormModal with config table editor"
```

---

### Task 5: Create ProfilesTab

**Files:**
- Create: `frontend/src/pages/Templates/ProfilesTab.tsx`

**Context:** Renders inside TemplateForm as the "Profiles" tab. Shows a table of profiles with CRUD actions.

- [ ] **Step 1: Create ProfilesTab.tsx**

```typescript
// frontend/src/pages/Templates/ProfilesTab.tsx

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
  const [editingProfile, setEditingProfile] = useState<SimulationProfile | null>(
    null,
  );

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
            <Button
              size="small"
              danger
              onClick={() => handleDelete(record)}
            >
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
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Templates/ProfilesTab.tsx
git commit -m "feat: add ProfilesTab with CRUD actions"
```

---

### Task 6: Add Profiles tab to TemplateForm

**Files:**
- Modify: `frontend/src/pages/Templates/TemplateForm.tsx`

**Context:** Currently TemplateForm renders a `Card` with title "Register Map". We need to wrap the Register Map and Profiles in an Ant Design `Tabs` component when viewing/editing an existing template. For new templates (create mode), keep the current layout (no profiles tab since the template doesn't exist yet).

- [ ] **Step 1: Add Tabs import and ProfilesTab import**

In `frontend/src/pages/Templates/TemplateForm.tsx`, update the antd import to include `Tabs`:

Replace:
```typescript
import { Button, Card, Form, Input, Select, Space, Tag, Typography } from "antd";
```
With:
```typescript
import { Button, Card, Form, Input, Select, Space, Tabs, Tag, Typography } from "antd";
```

Add import for ProfilesTab after the RegisterTable import:
```typescript
import { ProfilesTab } from "./ProfilesTab";
```

- [ ] **Step 2: Replace the Register Map Card with Tabs for edit/view mode**

Replace the Register Map Card section (lines 112–118 of the current file):

```typescript
      <Card title="Register Map" style={{ marginBottom: 16 }}>
        <RegisterTable
          registers={registers}
          onChange={setRegisters}
          disabled={isReadOnly}
        />
      </Card>
```

With:

```typescript
      {isEdit ? (
        <Card style={{ marginBottom: 16 }}>
          <Tabs
            defaultActiveKey="registers"
            items={[
              {
                key: "registers",
                label: "Register Map",
                children: (
                  <RegisterTable
                    registers={registers}
                    onChange={setRegisters}
                    disabled={isReadOnly}
                  />
                ),
              },
              {
                key: "profiles",
                label: "Profiles",
                children: id ? (
                  <ProfilesTab
                    templateId={id}
                    registers={registers}
                    readOnly={isReadOnly}
                  />
                ) : null,
              },
            ]}
          />
        </Card>
      ) : (
        <Card title="Register Map" style={{ marginBottom: 16 }}>
          <RegisterTable
            registers={registers}
            onChange={setRegisters}
            disabled={isReadOnly}
          />
        </Card>
      )}
```

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Templates/TemplateForm.tsx
git commit -m "feat: add Profiles tab to TemplateForm for edit/view mode"
```

---

## Chunk 3: Profile Selection in Device Creation

### Task 7: Add profile dropdown to CreateDeviceModal

**Files:**
- Modify: `frontend/src/pages/Devices/CreateDeviceModal.tsx`

**Context:** When a user selects a template, fetch profiles for that template and show a dropdown. Pre-select the default profile. Both single and batch tabs share the same profile selection.

- [ ] **Step 1: Add imports and profile state**

In `frontend/src/pages/Devices/CreateDeviceModal.tsx`, add the profileStore import:

```typescript
import { useProfileStore } from "../../stores/profileStore";
```

Inside the component, after the existing store hooks, add:

```typescript
  const { profiles, loading: profilesLoading, fetchProfiles, clearProfiles } =
    useProfileStore();
  const [selectedProfileId, setSelectedProfileId] = useState<
    string | null | undefined
  >(undefined);
```

- [ ] **Step 2: Add template change handler**

Add a handler that fetches profiles when template changes, and a reset when modal closes. After the existing `useEffect`:

```typescript
  const handleTemplateChange = (templateId: string) => {
    fetchProfiles(templateId);
    setSelectedProfileId(undefined); // will be set after profiles load
  };

  // Pre-select default profile when profiles load
  useEffect(() => {
    if (profiles.length > 0) {
      const defaultProfile = profiles.find((p) => p.is_default);
      setSelectedProfileId(defaultProfile?.id ?? undefined);
    } else {
      setSelectedProfileId(undefined);
    }
  }, [profiles]);

  // Clean up on close
  useEffect(() => {
    if (!open) {
      clearProfiles();
      setSelectedProfileId(undefined);
    }
  }, [open, clearProfiles]);
```

- [ ] **Step 3: Build profile options**

After `templateOptions`, add:

```typescript
  const profileOptions = [
    { value: "__none__", label: "None (no profile)" },
    ...profiles.map((p) => ({
      value: p.id,
      label: `${p.name}${p.is_default ? " (default)" : ""}${p.is_builtin ? " [built-in]" : ""}`,
    })),
  ];
```

- [ ] **Step 4: Inject profile_id into submit handlers**

Update `handleSingleSubmit`:

```typescript
  const handleSingleSubmit = async () => {
    const values = await singleForm.validateFields();
    // Inject profile_id from shared state
    if (selectedProfileId === "__none__") {
      values.profile_id = null;
    } else if (selectedProfileId) {
      values.profile_id = selectedProfileId;
    }
    // else: omit profile_id entirely (backend auto-applies default)
    const result = await createDevice(values);
    if (result) {
      singleForm.resetFields();
      await fetchDevices();
      onClose();
    }
  };
```

Update `handleBatchSubmit` similarly:

```typescript
  const handleBatchSubmit = async () => {
    const values = await batchForm.validateFields();
    if (selectedProfileId === "__none__") {
      values.profile_id = null;
    } else if (selectedProfileId) {
      values.profile_id = selectedProfileId;
    }
    const success = await batchCreateDevices(values);
    if (success) {
      batchForm.resetFields();
      await fetchDevices();
      onClose();
    }
  };
```

- [ ] **Step 5: Add template onChange and profile dropdown to single tab**

Update the template `Select` in the single tab to trigger profile fetch:

```typescript
                <Form.Item
                  name="template_id"
                  label="Template"
                  rules={[{ required: true }]}
                >
                  <Select
                    options={templateOptions}
                    placeholder="Select template"
                    onChange={handleTemplateChange}
                  />
                </Form.Item>
```

Add the profile dropdown right after the template Form.Item (before the name field):

```typescript
                {profiles.length > 0 && (
                  <Form.Item label="Simulation Profile">
                    <Select
                      options={profileOptions}
                      value={selectedProfileId ?? undefined}
                      onChange={(v) => setSelectedProfileId(v)}
                      placeholder={
                        profilesLoading
                          ? "Loading profiles..."
                          : "Select profile"
                      }
                      loading={profilesLoading}
                      disabled={profilesLoading}
                      style={{ width: "100%" }}
                    />
                  </Form.Item>
                )}
```

- [ ] **Step 6: Add template onChange and profile dropdown to batch tab**

Same changes to the batch tab — update the template Select `onChange` and add the profile dropdown after it:

```typescript
                <Form.Item
                  name="template_id"
                  label="Template"
                  rules={[{ required: true }]}
                >
                  <Select
                    options={templateOptions}
                    placeholder="Select template"
                    onChange={handleTemplateChange}
                  />
                </Form.Item>
                {profiles.length > 0 && (
                  <Form.Item label="Simulation Profile">
                    <Select
                      options={profileOptions}
                      value={selectedProfileId ?? undefined}
                      onChange={(v) => setSelectedProfileId(v)}
                      placeholder={
                        profilesLoading
                          ? "Loading profiles..."
                          : "Select profile"
                      }
                      loading={profilesLoading}
                      disabled={profilesLoading}
                      style={{ width: "100%" }}
                    />
                  </Form.Item>
                )}
```

- [ ] **Step 7: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/pages/Devices/CreateDeviceModal.tsx
git commit -m "feat: add profile dropdown to CreateDeviceModal"
```

---

## Chunk 4: Build Verification and Docs

### Task 8: Full build verification

- [ ] **Step 1: Run TypeScript check**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors.

- [ ] **Step 2: Run Vite build**

Run: `cd frontend && npx vite build`
Expected: Build succeeds with no errors.

- [ ] **Step 3: Run backend tests to ensure nothing is broken**

Run: `docker run --rm --network ghostmeter_default -e DATABASE_URL=postgresql+asyncpg://ghostmeter:ghostmeter@postgres:5432/ghostmeter_test -v "$(pwd)/backend:/app" -w /app ghostmeter-backend python -m pytest tests/ -q`
Expected: 229 passed.

---

### Task 9: Update documentation

**Files:**
- Modify: `docs/development-phases.md`
- Modify: `docs/development-log.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Mark Milestone 8.3 complete in development-phases.md**

Replace the Phase 8.3 section:

```markdown
### Milestone 8.3：Frontend Profile Selector (#13) ✅
- [x] Profile selector dropdown in device creation UI (single + batch)
- [x] Profile management page (Profiles tab in template detail)
- [x] ProfileFormModal with per-register config editor
- [x] Profile Zustand store + API client
```

- [ ] **Step 2: Add development log entry**

Add to top of `docs/development-log.md`:

```markdown
## 2026-03-25 — Frontend Profile Selector (Phase 8.3)

### What was done
- **Profile types, API client, store**: New `profile.ts` types, `profileApi.ts`, `profileStore.ts` following existing patterns
- **ProfilesTab**: Profile list table in template detail with edit/delete/set-default actions, built-in protection
- **ProfileFormModal**: Create/edit modal with per-register config table (reuses DataModeTab pattern)
- **TemplateForm Tabs**: Wrapped Register Map + Profiles in Tabs for edit/view mode
- **CreateDeviceModal profile dropdown**: Fetches profiles on template change, pre-selects default, shared between single/batch tabs
- **Device types**: Added `profile_id` to `CreateDevice` and `BatchCreateDevice`

### Decisions
- Profile dropdown hidden when template has zero profiles (clean UX)
- Shared profile state between single/batch tabs (not per-form)
- Built-in profile configs are read-only in modal; name/description still editable
```

- [ ] **Step 3: Add CHANGELOG entries**

Under `## [Unreleased]` → `### Added`:

```markdown
- Profile management UI: Profiles tab in template detail with full CRUD
- Profile config editor: per-register data mode, params, interval, enabled toggle
- Profile selector dropdown in device creation (single + batch), auto-selects default profile
```

- [ ] **Step 4: Commit docs**

```bash
git add docs/development-phases.md docs/development-log.md CHANGELOG.md
git commit -m "docs: update docs for frontend profile selector (Phase 8.3)"
```
