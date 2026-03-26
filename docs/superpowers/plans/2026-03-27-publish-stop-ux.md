# Publish/Stop UX Unification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unify the start/stop UX across Modbus and MQTT with consistent visuals, MQTT edit/publish mode separation, and MQTT status indicators in the device list and detail pages.

**Architecture:** Frontend-focused changes with one backend addition (`mqtt_publishing` field on device list response). The MQTT Card gets two modes (editing vs publishing). Device List and Detail pages get MQTT status tags.

**Tech Stack:** React 18, Ant Design 5, TypeScript, FastAPI, SQLAlchemy

---

## File Structure

### Backend (1 schema change + 1 service change)
- **Modify:** `backend/app/schemas/device.py` — add `mqtt_publishing: bool` to `DeviceSummary`
- **Modify:** `backend/app/services/device_service.py` — LEFT JOIN `mqtt_publish_configs` in `list_devices()` and `_device_to_summary()`
- **Test:** `backend/tests/test_devices.py` — verify `mqtt_publishing` field in list response

### Frontend (3 component changes + 1 type change)
- **Modify:** `frontend/src/types/device.ts` — add `mqtt_publishing` to `DeviceSummary`
- **Modify:** `frontend/src/pages/Devices/MqttPublishConfig.tsx` — edit/publish mode separation
- **Modify:** `frontend/src/pages/Devices/DeviceList.tsx` — MQTT status tag in Status column
- **Modify:** `frontend/src/pages/Devices/DeviceDetail.tsx` — MQTT status tag in header

---

### Task 1: Backend — Add `mqtt_publishing` to device list response

**Files:**
- Modify: `backend/app/schemas/device.py:78-91`
- Modify: `backend/app/services/device_service.py:78-134`
- Test: `backend/tests/test_devices.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_devices.py`:

```python
class TestDeviceMqttPublishing:
    async def test_list_devices_includes_mqtt_publishing_false_by_default(
        self, client: AsyncClient,
    ) -> None:
        """Devices without MQTT config should have mqtt_publishing=False."""
        template = await create_template(client)
        await create_device(client, template["id"])

        resp = await client.get("/api/v1/devices")
        assert resp.status_code == 200
        devices = resp.json()["data"]
        assert len(devices) >= 1
        assert devices[0]["mqtt_publishing"] is False

    async def test_list_devices_mqtt_publishing_reflects_enabled_config(
        self, client: AsyncClient,
    ) -> None:
        """Devices with enabled MQTT config should have mqtt_publishing=True."""
        template = await create_template(client)
        device = await create_device(client, template["id"])

        # Create MQTT config with enabled=true via PUT then start
        await client.put(
            f"/api/v1/system/devices/{device['id']}/mqtt",
            json={
                "topic_template": "test/{device_name}",
                "payload_mode": "batch",
                "publish_interval_seconds": 5,
                "qos": 0,
                "retain": False,
            },
        )
        # The enabled flag is set by start endpoint, but we can check the DB field.
        # After PUT, enabled defaults to False, so mqtt_publishing should be False.
        resp = await client.get("/api/v1/devices")
        devices = resp.json()["data"]
        target = [d for d in devices if d["id"] == device["id"]][0]
        assert target["mqtt_publishing"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_devices.py::TestDeviceMqttPublishing -v`
Expected: FAIL — `KeyError: 'mqtt_publishing'`

- [ ] **Step 3: Add `mqtt_publishing` field to `DeviceSummary` schema**

In `backend/app/schemas/device.py`, add field to `DeviceSummary`:

```python
class DeviceSummary(BaseModel):
    """Schema for device list items."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    template_id: UUID
    template_name: str
    name: str
    slave_id: int
    status: str
    port: int
    description: str | None
    mqtt_publishing: bool = False
    created_at: datetime
    updated_at: datetime
```

- [ ] **Step 4: Update `_device_to_summary` and `list_devices` in device service**

In `backend/app/services/device_service.py`:

Update imports to include MqttPublishConfig:

```python
from app.models.mqtt import MqttPublishConfig
```

Update `_device_to_summary` to accept `mqtt_publishing` parameter:

```python
def _device_to_summary(
    device: DeviceInstance,
    template_name: str,
    mqtt_publishing: bool = False,
) -> dict:
    """Convert device ORM to summary dict."""
    return {
        "id": device.id,
        "template_id": device.template_id,
        "template_name": template_name,
        "name": device.name,
        "slave_id": device.slave_id,
        "status": device.status,
        "port": device.port,
        "description": device.description,
        "mqtt_publishing": mqtt_publishing,
        "created_at": device.created_at,
        "updated_at": device.updated_at,
    }
```

Update `list_devices` to LEFT JOIN mqtt_publish_configs:

```python
async def list_devices(session: AsyncSession) -> list[dict]:
    """List all devices with template name and MQTT publishing status."""
    stmt = (
        select(
            DeviceInstance,
            DeviceTemplate.name.label("template_name"),
            MqttPublishConfig.enabled.label("mqtt_enabled"),
        )
        .join(DeviceTemplate, DeviceInstance.template_id == DeviceTemplate.id)
        .outerjoin(
            MqttPublishConfig,
            DeviceInstance.id == MqttPublishConfig.device_id,
        )
        .order_by(DeviceInstance.created_at)
    )
    result = await session.execute(stmt)
    return [
        _device_to_summary(
            row.DeviceInstance,
            row.template_name,
            mqtt_publishing=bool(row.mqtt_enabled),
        )
        for row in result.all()
    ]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_devices.py::TestDeviceMqttPublishing -v`
Expected: PASS

- [ ] **Step 6: Run full device test suite to check for regressions**

Run: `cd backend && python -m pytest tests/test_devices.py -v`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/device.py backend/app/services/device_service.py backend/tests/test_devices.py
git commit -m "feat: add mqtt_publishing field to device list response (#11)"
```

---

### Task 2: Frontend — Add `mqtt_publishing` to TypeScript type

**Files:**
- Modify: `frontend/src/types/device.ts:1-12`

- [ ] **Step 1: Add `mqtt_publishing` field to `DeviceSummary` interface**

In `frontend/src/types/device.ts`:

```typescript
export interface DeviceSummary {
  id: string;
  template_id: string;
  template_name: string;
  name: string;
  slave_id: number;
  status: "stopped" | "running" | "error";
  port: number;
  description: string | null;
  mqtt_publishing: boolean;
  created_at: string;
  updated_at: string;
}
```

- [ ] **Step 2: Verify frontend compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/device.ts
git commit -m "feat: add mqtt_publishing to DeviceSummary type (#11)"
```

---

### Task 3: Frontend — MQTT Card edit/publish mode separation

**Files:**
- Modify: `frontend/src/pages/Devices/MqttPublishConfig.tsx`

- [ ] **Step 1: Rewrite MqttPublishConfig with edit/publish modes**

Replace the entire content of `frontend/src/pages/Devices/MqttPublishConfig.tsx`:

```tsx
import { PlayCircleOutlined, SaveOutlined, StopOutlined } from "@ant-design/icons";
import {
  Alert,
  Badge,
  Button,
  Card,
  Form,
  Input,
  InputNumber,
  Radio,
  Select,
  Space,
  Switch,
  Typography,
  message,
} from "antd";
import { useEffect, useState } from "react";
import { mqttApi } from "../../services/mqttApi";
import type { MqttPublishConfig as MqttConfig, MqttPublishConfigWrite } from "../../types/mqtt";

interface MqttPublishConfigProps {
  deviceId: string;
  onPublishStateChange?: (publishing: boolean) => void;
}

export function MqttPublishConfig({ deviceId, onPublishStateChange }: MqttPublishConfigProps) {
  const [form] = Form.useForm<MqttPublishConfigWrite>();
  const [config, setConfig] = useState<MqttConfig | null>(null);
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);

  useEffect(() => {
    loadConfig();
  }, [deviceId]);

  const loadConfig = async () => {
    try {
      const resp = await mqttApi.getDeviceConfig(deviceId);
      if (resp.data) {
        setConfig(resp.data);
        form.setFieldsValue({
          topic_template: resp.data.topic_template,
          payload_mode: resp.data.payload_mode,
          publish_interval_seconds: resp.data.publish_interval_seconds,
          qos: resp.data.qos,
          retain: resp.data.retain,
        });
      }
    } catch {
      // No config yet
    }
  };

  const updateConfig = (newConfig: MqttConfig) => {
    setConfig(newConfig);
    onPublishStateChange?.(newConfig.enabled);
  };

  const handleSave = async () => {
    setLoading(true);
    try {
      const values = await form.validateFields();
      const resp = await mqttApi.updateDeviceConfig(deviceId, values);
      if (resp.data) {
        updateConfig(resp.data);
        message.success("MQTT config saved");
      }
    } catch {
      message.error("Failed to save MQTT config");
    } finally {
      setLoading(false);
    }
  };

  const handleStart = async () => {
    setActionLoading(true);
    try {
      // Auto-save before starting
      const values = await form.validateFields();
      await mqttApi.updateDeviceConfig(deviceId, values);
      const resp = await mqttApi.startPublishing(deviceId);
      if (resp.data) {
        updateConfig(resp.data);
        message.success("MQTT publishing started");
      }
    } catch {
      message.error("Failed to start publishing. Check broker settings.");
    } finally {
      setActionLoading(false);
    }
  };

  const handleStop = async () => {
    setActionLoading(true);
    try {
      const resp = await mqttApi.stopPublishing(deviceId);
      if (resp.data) {
        updateConfig(resp.data);
        message.success("MQTT publishing stopped");
      }
    } catch {
      message.error("Failed to stop publishing");
    } finally {
      setActionLoading(false);
    }
  };

  const isPublishing = config?.enabled ?? false;

  return (
    <Card
      title={
        <Space>
          <span>MQTT Publishing</span>
          <Badge
            status={isPublishing ? "processing" : "default"}
            text={isPublishing ? "Publishing" : "Stopped"}
          />
        </Space>
      }
      style={{ marginTop: 16 }}
    >
      <Form
        form={form}
        layout="vertical"
        initialValues={{
          topic_template: "telemetry/{device_name}",
          payload_mode: "batch",
          publish_interval_seconds: 5,
          qos: 0,
          retain: false,
        }}
      >
        <Form.Item
          name="topic_template"
          label="Topic Template"
          rules={[{ required: true, message: "Required" }]}
        >
          <Input placeholder="telemetry/{device_name}" disabled={isPublishing} />
        </Form.Item>
        <Typography.Text type="secondary" style={{ display: "block", marginTop: -20, marginBottom: 16, fontSize: 12 }}>
          Variables: {"{device_name}"}, {"{slave_id}"}, {"{register_name}"}, {"{template_name}"}
        </Typography.Text>

        <Form.Item name="payload_mode" label="Payload Mode">
          <Radio.Group disabled={isPublishing}>
            <Radio value="batch">Batch (all registers in one message)</Radio>
            <Radio value="per_register">Per Register (one message per register)</Radio>
          </Radio.Group>
        </Form.Item>

        <Form.Item
          name="publish_interval_seconds"
          label="Publish Interval (seconds)"
          rules={[{ required: true, message: "Required" }]}
        >
          <InputNumber min={1} max={3600} style={{ width: "100%" }} disabled={isPublishing} />
        </Form.Item>

        <Form.Item name="qos" label="QoS Level">
          <Select disabled={isPublishing}>
            <Select.Option value={0}>0 — At most once</Select.Option>
            <Select.Option value={1}>1 — At least once</Select.Option>
            <Select.Option value={2}>2 — Exactly once</Select.Option>
          </Select>
        </Form.Item>

        <Form.Item name="retain" label="Retain" valuePropName="checked">
          <Switch disabled={isPublishing} />
        </Form.Item>

        {isPublishing && (
          <Alert
            message="Stop publishing to edit settings"
            type="info"
            showIcon
            style={{ marginBottom: 16 }}
          />
        )}

        <Space size="middle">
          {isPublishing ? (
            <Button
              danger
              type="primary"
              icon={<StopOutlined />}
              onClick={handleStop}
              loading={actionLoading}
              size="large"
            >
              Stop Publishing
            </Button>
          ) : (
            <>
              <Button
                icon={<SaveOutlined />}
                onClick={handleSave}
                loading={loading}
              >
                Save Config
              </Button>
              <Button
                type="primary"
                icon={<PlayCircleOutlined />}
                onClick={handleStart}
                loading={actionLoading}
                size="large"
                style={{ backgroundColor: "#52c41a", borderColor: "#52c41a" }}
              >
                Start Publishing
              </Button>
            </>
          )}
        </Space>
      </Form>
    </Card>
  );
}
```

Key changes from original:
- All form fields get `disabled={isPublishing}` prop
- `Alert` component shown when publishing: "Stop publishing to edit settings"
- `Save Config` button hidden during publishing (not needed in read-only mode)
- `handleStart` always saves before starting (auto-save)
- Added `onPublishStateChange` callback prop for parent component to react to state changes
- Removed `Save Config` button from publishing mode, keeping only `Stop Publishing`

- [ ] **Step 2: Verify frontend compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Devices/MqttPublishConfig.tsx
git commit -m "feat: MQTT card edit/publish mode separation (#11)"
```

---

### Task 4: Frontend — MQTT status tag in Device List

**Files:**
- Modify: `frontend/src/pages/Devices/DeviceList.tsx:1-9,126-135`

- [ ] **Step 1: Add Tag import and MQTT indicator to Status column**

In `frontend/src/pages/Devices/DeviceList.tsx`:

Add `Tag` to the antd imports:

```typescript
import { Badge, Button, Popconfirm, Space, Table, Tag, Tooltip } from "antd";
```

Update the Status column render function (replace the existing Status column definition):

```typescript
    {
      title: "Status",
      dataIndex: "status",
      key: "status",
      width: 160,
      render: (status: string, record: DeviceSummary) => {
        const config = STATUS_CONFIG[status] ?? STATUS_CONFIG.stopped;
        return (
          <Space size={4}>
            <Badge status={config.status} text={config.text} />
            {record.status === "running" && record.mqtt_publishing && (
              <Tag color="green" style={{ marginInlineStart: 0 }}>MQTT</Tag>
            )}
          </Space>
        );
      },
    },
```

- [ ] **Step 2: Verify frontend compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Devices/DeviceList.tsx
git commit -m "feat: add MQTT publishing indicator to device list (#11)"
```

---

### Task 5: Frontend — MQTT status tag in Device Detail header

**Files:**
- Modify: `frontend/src/pages/Devices/DeviceDetail.tsx:1-11,84-136,149`

- [ ] **Step 1: Add Tag import, MQTT state, and status tag to header**

In `frontend/src/pages/Devices/DeviceDetail.tsx`:

Add `Tag` to antd imports:

```typescript
import { Badge, Button, Card, Descriptions, Space, Table, Tag, Typography } from "antd";
```

Add `mqttPublishing` state inside the `DeviceDetail` component, after the existing state declarations:

```typescript
const [mqttPublishing, setMqttPublishing] = useState(false);
```

Update the Status `Descriptions.Item` to include the MQTT tag (replace the existing Status item):

```typescript
          <Descriptions.Item label="Status">
            <Space size={4}>
              <Badge status={statusConfig.status} text={statusConfig.text} />
              {currentDevice?.status === "running" && mqttPublishing && (
                <Tag color="green">MQTT Publishing</Tag>
              )}
            </Space>
          </Descriptions.Item>
```

Update the `MqttPublishConfig` usage to pass `onPublishStateChange` (replace the existing line):

```typescript
      {id && (
        <MqttPublishConfig
          deviceId={id}
          onPublishStateChange={setMqttPublishing}
        />
      )}
```

- [ ] **Step 2: Verify frontend compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Devices/DeviceDetail.tsx
git commit -m "feat: add MQTT status tag to device detail header (#11)"
```

---

### Task 6: Final verification and docs

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `docs/development-log.md`
- Modify: `docs/api-reference.md`

- [ ] **Step 1: Run full backend test suite**

Run: `cd backend && python -m pytest -v`
Expected: All tests PASS

- [ ] **Step 2: Build frontend**

Run: `cd frontend && npm run build`
Expected: Build succeeds with no errors

- [ ] **Step 3: Update CHANGELOG.md**

Add under `## [Unreleased]` (create this section if it doesn't exist after the `[0.3.0]` header):

```markdown
## [Unreleased]

### Changed
- MQTT publish config card: edit/publish mode separation — fields locked during publishing, "Stop publishing to edit settings" hint
- MQTT publishing status indicator (green `MQTT` tag) in device list and device detail pages
- `mqtt_publishing` boolean field added to device list API response
- Unified button styles: Start Publishing uses green primary, Stop Publishing uses danger
```

- [ ] **Step 4: Update docs/development-log.md**

Append a new entry:

```markdown
## 2026-03-27 — Publish/Stop UX Unification (#11)

### What was done
- MQTT card redesigned with edit/publish mode separation
  - All form fields disabled during publishing
  - Info alert: "Stop publishing to edit settings"
  - Auto-save on Start Publishing
- Device list: added `mqtt_publishing` boolean to API response (LEFT JOIN mqtt_publish_configs)
- Device list: green MQTT tag shown for devices actively publishing
- Device detail: MQTT Publishing tag shown in status area
- Button style unification (green primary for start, danger for stop)

### Decisions
- Kept Modbus and MQTT architecturally separated (no state machine changes)
- Used LEFT JOIN + boolean field instead of N+1 frontend queries for MQTT status
- MQTT tag only shown when device is running AND mqtt_publishing is true
```

- [ ] **Step 5: Update docs/api-reference.md**

Find the `DeviceSummary` schema section and add `mqtt_publishing`:

```markdown
| mqtt_publishing | boolean | Whether MQTT publishing is enabled for this device |
```

- [ ] **Step 6: Commit docs**

```bash
git add CHANGELOG.md docs/development-log.md docs/api-reference.md
git commit -m "docs: update docs for Publish/Stop UX unification (#11)"
```
