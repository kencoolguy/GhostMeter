# Monitor Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the `/monitor` page as a glance dashboard and the app's home page (issue #29).

**Architecture:** Frontend-heavy refactor with two small backend changes (include stopped devices in WebSocket snapshot, expose MQTT broker connection state). Replaces in-page detail expansion with cards that navigate to `/devices/{id}`. New components: `KpiPanel`, `Sparkline`, `EventToast`, `EventDrawer`, `EmptyState`. Removes `DeviceDetailPanel`, `RegisterChart`, `StatsPanel`.

**Tech Stack:** Backend — FastAPI + pytest. Frontend — React 19 + TypeScript + Ant Design 5 + Zustand + recharts + Playwright (e2e only, no unit test framework).

**Spec:** `docs/superpowers/specs/2026-04-17-monitor-redesign-design.md`

**Branch:** `feature/claude-monitor-redesign-20260417` (already created from `dev`)

---

## File Map

**Backend — modify:**
- `backend/app/services/monitor_service.py` — remove stopped filter, add `mqtt_broker_connected`
- `backend/tests/test_monitor_service.py` — NEW

**Frontend — create:**
- `frontend/src/pages/Monitor/Sparkline.tsx`
- `frontend/src/pages/Monitor/KpiPanel.tsx`
- `frontend/src/pages/Monitor/EmptyState.tsx`
- `frontend/src/pages/Monitor/EventToast.tsx`
- `frontend/src/pages/Monitor/EventDrawer.tsx`

**Frontend — rewrite:**
- `frontend/src/pages/Monitor/index.tsx`
- `frontend/src/pages/Monitor/DeviceCard.tsx`
- `frontend/src/pages/Monitor/DeviceCardGrid.tsx`
- `frontend/src/stores/monitorStore.ts`
- `frontend/src/types/monitor.ts`
- `frontend/src/App.tsx` (route `/` redirect)
- `frontend/src/layouts/MainLayout.tsx` (sidebar order)

**Frontend — delete:**
- `frontend/src/pages/Monitor/DeviceDetailPanel.tsx`
- `frontend/src/pages/Monitor/RegisterChart.tsx`
- `frontend/src/pages/Monitor/StatsPanel.tsx`

**Tests:**
- `frontend/e2e/smoke.spec.ts` — update existing Monitor smoke; add empty-state/with-device assertions

**Docs:**
- `CHANGELOG.md`, `docs/development-log.md`, `docs/development-phases.md`, `docs/api-reference.md` (no DB schema changes)

---

## Task 1: Backend — include stopped devices in monitor snapshot

**Files:**
- Modify: `backend/app/services/monitor_service.py:78` (remove `where(...status != "stopped")`)
- Test: `backend/tests/test_monitor_service.py` (new file)

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_monitor_service.py`:

```python
"""Tests for monitor_service snapshot aggregation."""
import pytest
from httpx import AsyncClient

from app.services.monitor_service import monitor_service


async def _make_template(client: AsyncClient) -> dict:
    payload = {
        "name": "T-Stopped-Test",
        "protocol": "modbus_tcp",
        "registers": [
            {
                "name": "voltage", "address": 0, "function_code": 4,
                "data_type": "float32", "byte_order": "big_endian",
                "scale_factor": 1.0, "unit": "V", "description": "",
                "sort_order": 0,
            },
        ],
    }
    r = await client.post("/api/v1/templates", json=payload)
    assert r.status_code == 201
    return r.json()["data"]


async def _make_device(client: AsyncClient, template_id: str, name: str, slave_id: int) -> dict:
    r = await client.post(
        "/api/v1/devices",
        json={"template_id": template_id, "name": name, "slave_id": slave_id, "port": 5020},
    )
    assert r.status_code == 201
    return r.json()["data"]


@pytest.mark.asyncio
async def test_snapshot_includes_stopped_devices(client: AsyncClient) -> None:
    """Stopped devices must appear in monitor snapshot (not filtered out)."""
    tpl = await _make_template(client)
    device = await _make_device(client, tpl["id"], "Stopped-Meter", 11)
    # Newly created devices default to status='stopped'

    snapshot = await monitor_service.get_snapshot()

    device_ids = [d["device_id"] for d in snapshot["devices"]]
    assert device["id"] in device_ids, "Stopped device should appear in snapshot"

    found = next(d for d in snapshot["devices"] if d["device_id"] == device["id"])
    assert found["status"] == "stopped"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && pytest tests/test_monitor_service.py::test_snapshot_includes_stopped_devices -v
```

Expected: FAIL — `assert <id> in [...]` fails because monitor service filters out stopped devices.

- [ ] **Step 3: Remove the stopped filter**

Edit `backend/app/services/monitor_service.py` — change lines 75-79 from:

```python
            stmt = (
                select(DeviceInstance)
                .options(selectinload(DeviceInstance.template).selectinload(DeviceTemplate.registers))
                .where(DeviceInstance.status != "stopped")
            )
```

to:

```python
            stmt = (
                select(DeviceInstance)
                .options(selectinload(DeviceInstance.template).selectinload(DeviceTemplate.registers))
            )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && pytest tests/test_monitor_service.py::test_snapshot_includes_stopped_devices -v
```

Expected: PASS.

- [ ] **Step 5: Run the broader monitor/device tests to confirm nothing else broke**

```bash
cd backend && pytest tests/test_devices.py tests/test_monitor_service.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/monitor_service.py backend/tests/test_monitor_service.py
git commit -m "feat(monitor): include stopped devices in snapshot (issue #29)"
```

---

## Task 2: Backend — expose `mqtt_broker_connected` in snapshot

**Files:**
- Modify: `backend/app/services/monitor_service.py` (within `get_snapshot`, add top-level field)
- Test: `backend/tests/test_monitor_service.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_monitor_service.py`:

```python
@pytest.mark.asyncio
async def test_snapshot_includes_mqtt_broker_connected(client: AsyncClient) -> None:
    """Snapshot must expose top-level mqtt_broker_connected boolean."""
    snapshot = await monitor_service.get_snapshot()
    assert "mqtt_broker_connected" in snapshot
    assert isinstance(snapshot["mqtt_broker_connected"], bool)
    # In test env the MQTT adapter has no broker configured → expect False
    assert snapshot["mqtt_broker_connected"] is False
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && pytest tests/test_monitor_service.py::test_snapshot_includes_mqtt_broker_connected -v
```

Expected: FAIL — `KeyError` or `assert "mqtt_broker_connected" in {...}` is False.

- [ ] **Step 3: Add the field to `get_snapshot`**

Edit `backend/app/services/monitor_service.py` — at the end of `get_snapshot`, replace the final `return {...}` block (currently lines 151-156) with:

```python
        # MQTT broker connection state
        mqtt_adapter = protocol_manager.get_adapter("mqtt")
        mqtt_broker_connected = False
        if mqtt_adapter is not None:
            try:
                mqtt_broker_connected = bool(mqtt_adapter.get_status().get("connected", False))
            except Exception:  # pragma: no cover — defensive
                logger.warning("Failed to read MQTT adapter status", exc_info=True)

        return {
            "type": "monitor_update",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "devices": devices_data,
            "events": self.get_events(),
            "mqtt_broker_connected": mqtt_broker_connected,
        }
```

If `protocol_manager` does not have a `get_adapter` method, check existing usage near line 69 (`from app.protocols import protocol_manager`) — fall back to:

```python
        mqtt_adapter = getattr(protocol_manager, "_adapters", {}).get("mqtt")
```

(verify in `backend/app/protocols/__init__.py` first; use the cleanest accessor available.)

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && pytest tests/test_monitor_service.py -v
```

Expected: all tests in this file PASS.

- [ ] **Step 5: Run the full backend test suite to catch regressions**

```bash
cd backend && pytest -q
```

Expected: all green (or only pre-existing failures unrelated to this change).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/monitor_service.py backend/tests/test_monitor_service.py
git commit -m "feat(monitor): add mqtt_broker_connected to snapshot (issue #29)"
```

---

## Task 3: Frontend types — extend monitor types

**Files:**
- Modify: `frontend/src/types/monitor.ts`

- [ ] **Step 1: Add `mqtt_stats` to `DeviceMonitorData` and `mqtt_broker_connected` to `MonitorUpdate`**

Edit `frontend/src/types/monitor.ts`:

```typescript
// --- Monitor Dashboard Types ---

export interface RegisterData {
  name: string;
  value: number;
  unit: string;
}

export interface CommunicationStats {
  request_count: number;
  success_count: number;
  error_count: number;
  avg_response_ms: number;
}

export interface MqttStats {
  request_count: number;
  success_count: number;
  error_count: number;
}

export interface FaultInfo {
  fault_type: string;
  params: Record<string, unknown>;
}

export interface DeviceMonitorData {
  device_id: string;
  name: string;
  slave_id: number;
  port: number;
  status: string;
  registers: RegisterData[];
  active_anomalies: string[];
  active_fault: FaultInfo | null;
  stats: CommunicationStats;
  mqtt_stats: MqttStats | null;
}

export interface MonitorEvent {
  timestamp: string;
  device_id: string;
  device_name: string;
  event_type: string;
  detail: string;
}

export interface MonitorUpdate {
  type: "monitor_update";
  timestamp: string;
  devices: DeviceMonitorData[];
  events: MonitorEvent[];
  mqtt_broker_connected: boolean;
}

export interface RegisterHistoryPoint {
  timestamp: number; // Date.now() ms
  value: number;
}
```

- [ ] **Step 2: Verify TypeScript build**

```bash
cd frontend && npm run build
```

Expected: build succeeds. (Errors elsewhere mean later tasks will pick them up — that's fine, this commit just ships the types.)

If `tsc -b` complains about an unrelated file, leave it for the relevant task to address. But this file's edits should compile cleanly.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/monitor.ts
git commit -m "feat(monitor): add mqtt_stats and mqtt_broker_connected types (issue #29)"
```

---

## Task 4: Routing & sidebar — make `/monitor` the home

**Files:**
- Modify: `frontend/src/App.tsx:28`
- Modify: `frontend/src/layouts/MainLayout.tsx:17-24`

- [ ] **Step 1: Change root redirect**

Edit `frontend/src/App.tsx` line 28 from:

```tsx
        <Route path="/" element={<Navigate to="/templates" replace />} />
```

to:

```tsx
        <Route path="/" element={<Navigate to="/monitor" replace />} />
```

- [ ] **Step 2: Reorder sidebar — Monitor first**

Edit `frontend/src/layouts/MainLayout.tsx` lines 17-24 from:

```tsx
const menuItems = [
  { key: "/templates", icon: <AppstoreOutlined />, label: "Templates" },
  { key: "/devices", icon: <HddOutlined />, label: "Devices" },
  { key: "/simulation", icon: <ExperimentOutlined />, label: "Simulation" },
  { key: "/scenarios", icon: <ThunderboltOutlined />, label: "Scenarios" },
  { key: "/monitor", icon: <DashboardOutlined />, label: "Monitor" },
  { key: "/settings", icon: <SettingOutlined />, label: "Settings" },
];
```

to:

```tsx
const menuItems = [
  { key: "/monitor", icon: <DashboardOutlined />, label: "Monitor" },
  { key: "/devices", icon: <HddOutlined />, label: "Devices" },
  { key: "/templates", icon: <AppstoreOutlined />, label: "Templates" },
  { key: "/simulation", icon: <ExperimentOutlined />, label: "Simulation" },
  { key: "/scenarios", icon: <ThunderboltOutlined />, label: "Scenarios" },
  { key: "/settings", icon: <SettingOutlined />, label: "Settings" },
];
```

- [ ] **Step 3: Verify build**

```bash
cd frontend && npm run build
```

Expected: PASS.

- [ ] **Step 4: Manual smoke**

Start dev server (`cd frontend && npm run dev`), open `http://localhost:5173/`. Expected: redirected to `/monitor`. Sidebar shows Monitor at the top.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/App.tsx frontend/src/layouts/MainLayout.tsx
git commit -m "feat(monitor): make /monitor the home route and first sidebar item (issue #29)"
```

---

## Task 5: Sparkline component

**Files:**
- Create: `frontend/src/pages/Monitor/Sparkline.tsx`

- [ ] **Step 1: Create the component**

```tsx
import { useMemo } from "react";
import { Line, LineChart, ResponsiveContainer } from "recharts";
import type { RegisterHistoryPoint } from "../../types";

interface SparklineProps {
  data: RegisterHistoryPoint[];
  color?: string;
  height?: number;
}

/**
 * Tiny in-card line chart. No axes, no grid, no tooltip.
 * Animation disabled so 1Hz updates don't jitter.
 */
export function Sparkline({ data, color = "#22d3ee", height = 36 }: SparklineProps) {
  const chartData = useMemo(
    () => data.map((p) => ({ value: p.value })),
    [data],
  );

  if (chartData.length < 2) {
    return <div style={{ height, opacity: 0.3 }} />;
  }

  return (
    <div style={{ width: "100%", height }}>
      <ResponsiveContainer>
        <LineChart data={chartData} margin={{ top: 2, right: 2, bottom: 2, left: 2 }}>
          <Line
            type="monotone"
            dataKey="value"
            stroke={color}
            dot={false}
            strokeWidth={1.5}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && npm run build
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Monitor/Sparkline.tsx
git commit -m "feat(monitor): add Sparkline component (issue #29)"
```

---

## Task 6: KpiPanel component

**Files:**
- Create: `frontend/src/pages/Monitor/KpiPanel.tsx`

- [ ] **Step 1: Create the component**

```tsx
import { useMemo } from "react";
import type { DeviceMonitorData } from "../../types";

interface KpiPanelProps {
  devices: DeviceMonitorData[];
  mqttBrokerConnected: boolean;
  pushFreqHz?: number;
}

interface KpiTileProps {
  label: string;
  value: number | string;
  tone?: "default" | "ok" | "err";
  sub?: string;
}

function KpiTile({ label, value, tone = "default", sub }: KpiTileProps) {
  const valueColor =
    tone === "ok" ? "#34d399" : tone === "err" ? "#fb7185" : "#e6edf5";
  return (
    <div
      style={{
        background: "#121826",
        border: "1px solid rgba(148,163,184,0.08)",
        borderRadius: 8,
        padding: "12px 14px",
      }}
    >
      <div
        style={{
          fontSize: 10,
          color: "#5f6b80",
          textTransform: "uppercase",
          letterSpacing: 0.5,
        }}
      >
        {label}
      </div>
      <div
        style={{
          fontSize: 24,
          color: valueColor,
          fontFamily: "'JetBrains Mono', monospace",
          fontWeight: 600,
          marginTop: 2,
        }}
      >
        {value}
      </div>
      {sub && <div style={{ fontSize: 9, color: "#5f6b80", marginTop: 2 }}>{sub}</div>}
    </div>
  );
}

interface PillProps {
  text: string;
  tone: "warn" | "danger" | "ok" | "muted";
}

function Pill({ text, tone }: PillProps) {
  const palette = {
    warn: { border: "rgba(251,191,36,0.4)", color: "#fbbf24", dot: "#fbbf24" },
    danger: { border: "rgba(251,113,133,0.4)", color: "#fb7185", dot: "#fb7185" },
    ok: { border: "rgba(52,211,153,0.4)", color: "#34d399", dot: "#34d399" },
    muted: { border: "rgba(148,163,184,0.25)", color: "#9aa5b8", dot: "#5f6b80" },
  }[tone];
  return (
    <span
      style={{
        background: "#121826",
        border: `1px solid ${palette.border}`,
        borderRadius: 14,
        padding: "4px 10px",
        fontSize: 10,
        color: palette.color,
        display: "inline-flex",
        alignItems: "center",
        gap: 5,
      }}
    >
      <span
        style={{
          display: "inline-block",
          width: 5,
          height: 5,
          borderRadius: "50%",
          background: palette.dot,
        }}
      />
      {text}
    </span>
  );
}

export function KpiPanel({ devices, mqttBrokerConnected, pushFreqHz = 1 }: KpiPanelProps) {
  const stats = useMemo(() => {
    const running = devices.filter((d) => d.status === "running");
    const stopped = devices.filter((d) => d.status === "stopped").length;
    const errors = devices.filter((d) => d.status === "error").length;
    const dps = running.reduce((sum, d) => sum + d.registers.length, 0) * pushFreqHz;
    const activeAnomalies = devices.reduce(
      (sum, d) => sum + d.active_anomalies.length,
      0,
    );
    const activeFaults = devices.filter((d) => d.active_fault !== null).length;
    return {
      running: running.length,
      stopped,
      errors,
      dps,
      activeAnomalies,
      activeFaults,
    };
  }, [devices, pushFreqHz]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10 }}>
        <KpiTile label="Running" value={stats.running} tone="ok" sub="活躍中設備" />
        <KpiTile label="Stopped" value={stats.stopped} sub="已停止" />
        <KpiTile label="Errors" value={stats.errors} tone={stats.errors > 0 ? "err" : "default"} sub="異常設備" />
        <KpiTile label="Data Points / sec" value={stats.dps} sub="即時資料速率" />
      </div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {stats.activeAnomalies > 0 && (
          <Pill tone="warn" text={`${stats.activeAnomalies} active anomal${stats.activeAnomalies === 1 ? "y" : "ies"}`} />
        )}
        {stats.activeFaults > 0 && (
          <Pill tone="danger" text={`${stats.activeFaults} active fault${stats.activeFaults === 1 ? "" : "s"}`} />
        )}
        <Pill
          tone={mqttBrokerConnected ? "ok" : "muted"}
          text={mqttBrokerConnected ? "MQTT broker connected" : "MQTT broker not connected"}
        />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && npm run build
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Monitor/KpiPanel.tsx
git commit -m "feat(monitor): add KpiPanel with conditional pills (issue #29)"
```

---

## Task 7: EmptyState component

**Files:**
- Create: `frontend/src/pages/Monitor/EmptyState.tsx`

- [ ] **Step 1: Create the component**

```tsx
import { Button } from "antd";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { templateApi } from "../../services/templateApi";
import type { TemplateSummary } from "../../types";

/**
 * Shown when there are zero devices in the system.
 * Offers built-in template shortcuts and a "create device" CTA.
 */
export function EmptyState() {
  const navigate = useNavigate();
  const [builtins, setBuiltins] = useState<TemplateSummary[]>([]);

  useEffect(() => {
    let cancelled = false;
    templateApi
      .list()
      .then((res) => {
        if (cancelled) return;
        setBuiltins(res.data.filter((t) => t.is_builtin).slice(0, 3));
      })
      .catch(() => {
        if (!cancelled) setBuiltins([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div
      style={{
        textAlign: "center",
        padding: "60px 20px",
        color: "#9aa5b8",
      }}
    >
      <div style={{ fontSize: 48, opacity: 0.4, marginBottom: 12 }}>⚡</div>
      <div style={{ color: "#e6edf5", fontSize: 18, fontWeight: 600, marginBottom: 6 }}>
        還沒有設備
      </div>
      <div style={{ fontSize: 13, marginBottom: 18 }}>
        從內建模板快速建立第一台
      </div>

      {builtins.length > 0 && (
        <div
          style={{
            display: "flex",
            gap: 8,
            justifyContent: "center",
            flexWrap: "wrap",
            marginBottom: 18,
          }}
        >
          {builtins.map((t) => (
            <span
              key={t.id}
              onClick={() => navigate(`/devices?template=${t.id}`)}
              style={{
                padding: "6px 12px",
                background: "#121826",
                border: "1px solid rgba(34,211,238,0.3)",
                borderRadius: 6,
                fontSize: 11,
                color: "#22d3ee",
                cursor: "pointer",
              }}
            >
              {t.name}
            </span>
          ))}
        </div>
      )}

      <Button type="primary" onClick={() => navigate("/devices")}>
        + 建立設備
      </Button>
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && npm run build
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Monitor/EmptyState.tsx
git commit -m "feat(monitor): add EmptyState with builtin template shortcuts (issue #29)"
```

---

## Task 8: DeviceCard rewrite — mid density + animations + stopped state

**Files:**
- Modify: `frontend/src/pages/Monitor/DeviceCard.tsx` (full rewrite)
- Create: `frontend/src/pages/Monitor/monitor.css` (animation keyframes — module-scope CSS imported in MonitorPage)

- [ ] **Step 1: Create the CSS file with keyframes and value-flash animation**

Create `frontend/src/pages/Monitor/monitor.css`:

```css
/* Monitor page animations — scoped via class names with gm-mon- prefix */

@keyframes gm-mon-breath {
  0%, 100% { opacity: 0.45; box-shadow: 0 0 0 rgba(52, 211, 153, 0); }
  50%      { opacity: 1;    box-shadow: 0 0 12px rgba(52, 211, 153, 0.6); }
}

@keyframes gm-mon-err-blink {
  0%, 100% { opacity: 1; }
  50%      { opacity: 0.3; }
}

@keyframes gm-mon-value-flash {
  0%   { color: #a7f3d0; text-shadow: 0 0 12px rgba(34, 211, 238, 0.8); }
  100% { color: #22d3ee; text-shadow: none; }
}

@keyframes gm-mon-toast-in {
  from { opacity: 0; transform: translateX(20px); }
  to   { opacity: 1; transform: translateX(0); }
}

.gm-mon-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
  margin-right: 8px;
}

.gm-mon-dot-running {
  background: #34d399;
  animation: gm-mon-breath 2s ease-in-out infinite;
}

.gm-mon-dot-error {
  background: #fb7185;
  animation: gm-mon-err-blink 0.8s ease-in-out infinite;
}

.gm-mon-dot-stopped {
  background: #475569;
}

.gm-mon-value-flash {
  animation: gm-mon-value-flash 0.5s ease-out;
}

.gm-mon-card {
  transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
}

.gm-mon-card:hover {
  border-color: rgba(34, 211, 238, 0.4) !important;
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(34, 211, 238, 0.08);
}

.gm-mon-toast {
  animation: gm-mon-toast-in 0.3s ease-out;
}
```

- [ ] **Step 2: Rewrite `DeviceCard.tsx`**

Replace the entire contents of `frontend/src/pages/Monitor/DeviceCard.tsx`:

```tsx
import { App, Tag } from "antd";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { deviceApi } from "../../services/deviceApi";
import type { DeviceMonitorData, RegisterHistoryPoint } from "../../types";
import { Sparkline } from "./Sparkline";

interface DeviceCardProps {
  device: DeviceMonitorData;
  history: RegisterHistoryPoint[];
}

const PREFERRED = ["total_power", "ac_power", "total_energy"];

function pickPrimaryAndSecondary(device: DeviceMonitorData) {
  const names = device.registers.map((r) => r.name);
  const primary =
    PREFERRED.find((n) => names.includes(n)) ?? names[0] ?? null;
  const secondary =
    PREFERRED.find((n) => names.includes(n) && n !== primary) ??
    names.find((n) => n !== primary) ??
    null;
  return {
    primary: primary ? device.registers.find((r) => r.name === primary) ?? null : null,
    secondary: secondary ? device.registers.find((r) => r.name === secondary) ?? null : null,
  };
}

export function DeviceCard({ device, history }: DeviceCardProps) {
  const navigate = useNavigate();
  const { message } = App.useApp();
  const { primary, secondary } = pickPrimaryAndSecondary(device);

  // Value-flash detection
  const lastPrimaryValueRef = useRef<number | null>(null);
  const [flashKey, setFlashKey] = useState(0);
  useEffect(() => {
    if (!primary) return;
    if (
      lastPrimaryValueRef.current !== null &&
      lastPrimaryValueRef.current !== primary.value
    ) {
      setFlashKey((k) => k + 1);
    }
    lastPrimaryValueRef.current = primary.value;
  }, [primary]);

  const isStopped = device.status === "stopped";
  const isError = device.status === "error";

  const dotClass =
    "gm-mon-dot " +
    (device.status === "running"
      ? "gm-mon-dot-running"
      : isError
      ? "gm-mon-dot-error"
      : "gm-mon-dot-stopped");

  const cardStyle: React.CSSProperties = {
    background: "#121826",
    border: `1px solid ${isError ? "rgba(251,113,133,0.3)" : "rgba(148,163,184,0.12)"}`,
    borderRadius: 10,
    padding: 14,
    cursor: "pointer",
    position: "relative",
    opacity: isStopped ? 0.55 : 1,
  };

  const onCardClick = () => {
    navigate(`/devices/${device.device_id}`);
  };

  const onStartClick = async (e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await deviceApi.start(device.device_id);
      message.success(`Started ${device.name}`);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Unknown error";
      message.error(`Start failed: ${msg}`);
    }
  };

  const valueDisplay = (v: number | undefined) =>
    typeof v === "number" ? v.toFixed(1) : "—";

  return (
    <div className="gm-mon-card" style={cardStyle} onClick={onCardClick}>
      <span style={{ position: "absolute", top: 12, right: 12, color: "#5f6b80", fontSize: 14 }}>
        →
      </span>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span style={{ display: "flex", alignItems: "center", color: "#e6edf5", fontWeight: 600, fontSize: 14 }}>
          <span className={dotClass} />
          {device.name}
        </span>
        <span style={{ color: "#5f6b80", fontSize: 10 }}>slv {device.slave_id}</span>
      </div>

      {primary ? (
        <>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginTop: 10 }}>
            <span style={{ color: "#9aa5b8", fontSize: 11, textTransform: "uppercase", letterSpacing: 0.3 }}>
              {primary.name}
            </span>
            <span
              key={flashKey}
              className={flashKey > 0 ? "gm-mon-value-flash" : undefined}
              style={{
                color: isError ? "#fb7185" : "#22d3ee",
                fontFamily: "'JetBrains Mono', monospace",
                fontSize: 18,
                fontWeight: 600,
              }}
            >
              {valueDisplay(primary.value)}
              <span style={{ color: "#9aa5b8", fontSize: 11, marginLeft: 3, fontFamily: "Inter, sans-serif", fontWeight: 400 }}>
                {primary.unit}
              </span>
            </span>
          </div>
          <Sparkline data={history} />
          {secondary && (
            <div style={{ display: "flex", justifyContent: "space-between", marginTop: 6 }}>
              <span style={{ color: "#5f6b80", fontSize: 10 }}>{secondary.name}</span>
              <span style={{ color: "#9aa5b8", fontSize: 11, fontFamily: "'JetBrains Mono', monospace" }}>
                {valueDisplay(secondary.value)} {secondary.unit}
              </span>
            </div>
          )}
        </>
      ) : (
        <div style={{ color: "#5f6b80", fontSize: 11, marginTop: 10 }}>No registers</div>
      )}

      <div style={{ display: "flex", gap: 5, marginTop: 10, flexWrap: "wrap" }}>
        {device.mqtt_stats && (
          <Tag color={device.mqtt_stats.error_count > 0 ? "orange" : "cyan"} style={{ fontSize: 10 }}>
            {device.mqtt_stats.error_count > 0 ? "MQTT err" : "MQTT"}
          </Tag>
        )}
        {device.active_anomalies.map((a) => (
          <Tag key={a} color="orange" style={{ fontSize: 10 }}>
            {a}
          </Tag>
        ))}
        {device.active_fault && (
          <Tag color="red" style={{ fontSize: 10 }}>
            {device.active_fault.fault_type}
          </Tag>
        )}
      </div>

      {isStopped && (
        <span
          onClick={onStartClick}
          style={{
            display: "inline-block",
            marginTop: 10,
            padding: "4px 10px",
            borderRadius: 4,
            background: "rgba(52,211,153,0.12)",
            color: "#34d399",
            fontSize: 11,
            border: "1px solid rgba(52,211,153,0.3)",
            cursor: "pointer",
          }}
        >
          ▶ Start
        </span>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd frontend && npm run build
```

Expected: PASS. (`DeviceCardGrid.tsx` will still typecheck against the old `selected/onClick` props until we rewrite it in Task 11.)

If errors mention `DeviceCardGrid` referencing the removed `selected`/`onClick` props, that's expected — it's fixed in Task 11. For now, the build error is acceptable and will be cleared by Task 11. Skip this verification step if the only errors are in `DeviceCardGrid.tsx`.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Monitor/monitor.css frontend/src/pages/Monitor/DeviceCard.tsx
git commit -m "feat(monitor): rewrite DeviceCard with mid density and animations (issue #29)"
```

---

## Task 9: monitorStore extensions — toast and drawer state

**Files:**
- Modify: `frontend/src/stores/monitorStore.ts` (full rewrite)

- [ ] **Step 1: Replace store contents**

Replace the entire contents of `frontend/src/stores/monitorStore.ts`:

```typescript
import { create } from "zustand";
import type {
  DeviceMonitorData,
  MonitorEvent,
  MonitorUpdate,
  RegisterHistoryPoint,
} from "../types";

const MAX_HISTORY_POINTS = 300; // 5 minutes at 1Hz
const TOAST_EVENT_TYPES = new Set([
  "anomaly_inject",
  "fault_set",
  "device_start",
  "device_stop",
]);

// key: `${deviceId}:${registerName}`
type RegisterHistoryMap = Record<string, RegisterHistoryPoint[]>;

interface MonitorState {
  devices: DeviceMonitorData[];
  events: MonitorEvent[];
  registerHistory: RegisterHistoryMap;
  mqttBrokerConnected: boolean;
  recentToastEvent: MonitorEvent | null;
  eventDrawerOpen: boolean;

  handleMonitorUpdate: (update: MonitorUpdate) => void;
  dismissToast: () => void;
  openEventDrawer: () => void;
  closeEventDrawer: () => void;
  clearEvents: () => void;
}

function findNewestEventNotIn(
  next: MonitorEvent[],
  prev: MonitorEvent[],
): MonitorEvent | null {
  // Backend returns events newest-first (see monitor_service.get_events).
  // An event is "new" if its (timestamp, device_id, event_type) tuple is not in prev.
  if (next.length === 0) return null;
  const prevKeys = new Set(
    prev.map((e) => `${e.timestamp}|${e.device_id}|${e.event_type}`),
  );
  for (const e of next) {
    const key = `${e.timestamp}|${e.device_id}|${e.event_type}`;
    if (!prevKeys.has(key) && TOAST_EVENT_TYPES.has(e.event_type)) {
      return e;
    }
  }
  return null;
}

export const useMonitorStore = create<MonitorState>((set) => ({
  devices: [],
  events: [],
  registerHistory: {},
  mqttBrokerConnected: false,
  recentToastEvent: null,
  eventDrawerOpen: false,

  handleMonitorUpdate: (update: MonitorUpdate) => {
    set((state) => {
      const now = Date.now();
      const newHistory = { ...state.registerHistory };

      for (const device of update.devices) {
        for (const reg of device.registers) {
          const key = `${device.device_id}:${reg.name}`;
          const existing = newHistory[key] ?? [];
          const updated = [...existing, { timestamp: now, value: reg.value }];
          newHistory[key] =
            updated.length > MAX_HISTORY_POINTS
              ? updated.slice(updated.length - MAX_HISTORY_POINTS)
              : updated;
        }
      }

      const newToast = findNewestEventNotIn(update.events, state.events);

      return {
        devices: update.devices,
        events: update.events,
        registerHistory: newHistory,
        mqttBrokerConnected: update.mqtt_broker_connected,
        recentToastEvent: newToast ?? state.recentToastEvent,
      };
    });
  },

  dismissToast: () => set({ recentToastEvent: null }),
  openEventDrawer: () => set({ eventDrawerOpen: true }),
  closeEventDrawer: () => set({ eventDrawerOpen: false }),
  clearEvents: () => set({ events: [] }),
}));
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && npm run build
```

Expected: errors only in `pages/Monitor/index.tsx` referencing removed `selectedDeviceId` / `selectDevice`. That's fixed in Task 11.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/stores/monitorStore.ts
git commit -m "feat(monitor): extend store with toast and drawer state (issue #29)"
```

---

## Task 10: EventToast and EventDrawer components

**Files:**
- Create: `frontend/src/pages/Monitor/EventToast.tsx`
- Create: `frontend/src/pages/Monitor/EventDrawer.tsx`

- [ ] **Step 1: Create `EventToast.tsx`**

```tsx
import { useEffect } from "react";
import type { MonitorEvent } from "../../types";

interface EventToastProps {
  event: MonitorEvent | null;
  onDismiss: () => void;
  onOpenDrawer: () => void;
  autoDismissMs?: number;
}

const TYPE_PALETTE: Record<string, { border: string; color: string; label: string }> = {
  anomaly_inject: { border: "#fbbf24", color: "#fbbf24", label: "⚠ Anomaly" },
  fault_set:      { border: "#fb7185", color: "#fb7185", label: "⚠ Fault" },
  device_start:   { border: "#34d399", color: "#34d399", label: "▶ Start" },
  device_stop:    { border: "#9aa5b8", color: "#9aa5b8", label: "■ Stop" },
};

export function EventToast({ event, onDismiss, onOpenDrawer, autoDismissMs = 3000 }: EventToastProps) {
  useEffect(() => {
    if (!event) return;
    const t = setTimeout(onDismiss, autoDismissMs);
    return () => clearTimeout(t);
  }, [event, onDismiss, autoDismissMs]);

  if (!event) return null;

  const palette = TYPE_PALETTE[event.event_type] ?? {
    border: "#22d3ee",
    color: "#22d3ee",
    label: event.event_type,
  };

  return (
    <div
      key={`${event.timestamp}-${event.device_id}-${event.event_type}`}
      className="gm-mon-toast"
      onClick={onOpenDrawer}
      style={{
        position: "fixed",
        top: 80,
        right: 24,
        width: 260,
        background: "#1a2030",
        border: `1px solid ${palette.border}`,
        borderRadius: 8,
        padding: "10px 12px",
        boxShadow: `0 0 24px ${palette.border}40`,
        cursor: "pointer",
        zIndex: 1000,
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: palette.color, marginBottom: 4 }}>
        <span>{palette.label}</span>
        <span style={{ color: "#5f6b80" }}>just now</span>
      </div>
      <div style={{ color: "#e6edf5", fontSize: 12 }}>
        <b>{event.device_name}</b> — {event.detail}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create `EventDrawer.tsx`**

```tsx
import { Button, Drawer, Empty, List, Tag, Typography } from "antd";
import type { MonitorEvent } from "../../types";

const { Text } = Typography;

const EVENT_COLORS: Record<string, string> = {
  device_start: "green",
  device_stop: "default",
  anomaly_inject: "orange",
  anomaly_clear: "blue",
  fault_set: "red",
  fault_clear: "blue",
};

interface EventDrawerProps {
  open: boolean;
  events: MonitorEvent[];
  onClose: () => void;
  onClear: () => void;
}

export function EventDrawer({ open, events, onClose, onClear }: EventDrawerProps) {
  return (
    <Drawer
      open={open}
      onClose={onClose}
      placement="right"
      width={360}
      title="Event Log"
      extra={
        <Button size="small" onClick={onClear} disabled={events.length === 0}>
          Clear
        </Button>
      }
    >
      {events.length === 0 ? (
        <Empty description="No events yet" />
      ) : (
        <List
          size="small"
          dataSource={events}
          renderItem={(e) => {
            const time = new Date(e.timestamp).toLocaleTimeString();
            return (
              <List.Item style={{ padding: "6px 0", display: "block" }}>
                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <Text type="secondary" style={{ fontSize: 11 }}>{time}</Text>
                  <Tag color={EVENT_COLORS[e.event_type] ?? "default"} style={{ fontSize: 10 }}>
                    {e.event_type}
                  </Tag>
                  <Text strong style={{ fontSize: 12 }}>{e.device_name}</Text>
                </div>
                <Text style={{ fontSize: 12 }}>{e.detail}</Text>
              </List.Item>
            );
          }}
        />
      )}
    </Drawer>
  );
}
```

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd frontend && npm run build
```

Expected: errors only remaining in `pages/Monitor/index.tsx` (fixed in Task 11).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Monitor/EventToast.tsx frontend/src/pages/Monitor/EventDrawer.tsx
git commit -m "feat(monitor): add EventToast and EventDrawer (issue #29)"
```

---

## Task 11: MonitorPage rewrite + DeviceCardGrid + cleanup

**Files:**
- Modify: `frontend/src/pages/Monitor/index.tsx` (full rewrite)
- Modify: `frontend/src/pages/Monitor/DeviceCardGrid.tsx` (full rewrite)
- Delete: `frontend/src/pages/Monitor/DeviceDetailPanel.tsx`
- Delete: `frontend/src/pages/Monitor/RegisterChart.tsx`
- Delete: `frontend/src/pages/Monitor/StatsPanel.tsx`

- [ ] **Step 1: Rewrite `DeviceCardGrid.tsx`**

```tsx
import type { DeviceMonitorData, RegisterHistoryPoint } from "../../types";
import { DeviceCard } from "./DeviceCard";

interface DeviceCardGridProps {
  devices: DeviceMonitorData[];
  registerHistory: Record<string, RegisterHistoryPoint[]>;
}

const PREFERRED = ["total_power", "ac_power", "total_energy"];

function pickPrimaryName(device: DeviceMonitorData): string | null {
  const names = device.registers.map((r) => r.name);
  return PREFERRED.find((n) => names.includes(n)) ?? names[0] ?? null;
}

export function DeviceCardGrid({ devices, registerHistory }: DeviceCardGridProps) {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))",
        gap: 12,
      }}
    >
      {devices.map((device) => {
        const primary = pickPrimaryName(device);
        const history = primary
          ? registerHistory[`${device.device_id}:${primary}`] ?? []
          : [];
        return <DeviceCard key={device.device_id} device={device} history={history} />;
      })}
    </div>
  );
}
```

- [ ] **Step 2: Rewrite `index.tsx`**

```tsx
import { Badge, Button, Typography } from "antd";
import { useCallback } from "react";
import { useWebSocket } from "../../hooks/useWebSocket";
import { useMonitorStore } from "../../stores/monitorStore";
import type { MonitorUpdate } from "../../types";
import { DeviceCardGrid } from "./DeviceCardGrid";
import { EmptyState } from "./EmptyState";
import { EventDrawer } from "./EventDrawer";
import { EventToast } from "./EventToast";
import { KpiPanel } from "./KpiPanel";
import "./monitor.css";

const WS_URL = `ws://${window.location.hostname}:8000/ws/monitor`;

export default function MonitorPage() {
  const {
    devices,
    events,
    registerHistory,
    mqttBrokerConnected,
    recentToastEvent,
    eventDrawerOpen,
    handleMonitorUpdate,
    dismissToast,
    openEventDrawer,
    closeEventDrawer,
    clearEvents,
  } = useMonitorStore();

  const onMessage = useCallback(
    (data: unknown) => {
      const update = data as MonitorUpdate;
      if (update.type === "monitor_update") {
        handleMonitorUpdate(update);
      }
    },
    [handleMonitorUpdate],
  );

  const { connected } = useWebSocket({ url: WS_URL, onMessage });

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <Typography.Title level={2} style={{ margin: 0 }}>
          Monitor{" "}
          <Badge
            status={connected ? "success" : "error"}
            text={<span style={{ fontSize: 12 }}>{connected ? "Live" : "Disconnected"}</span>}
            style={{ marginLeft: 10 }}
          />
        </Typography.Title>
        <Button onClick={openEventDrawer}>
          📋 Events <span style={{ marginLeft: 4, color: "#9aa5b8" }}>({events.length})</span>
        </Button>
      </div>

      {devices.length === 0 ? (
        <EmptyState />
      ) : (
        <>
          <KpiPanel devices={devices} mqttBrokerConnected={mqttBrokerConnected} />
          <DeviceCardGrid devices={devices} registerHistory={registerHistory} />
        </>
      )}

      <EventToast
        event={recentToastEvent}
        onDismiss={dismissToast}
        onOpenDrawer={() => {
          dismissToast();
          openEventDrawer();
        }}
      />

      <EventDrawer
        open={eventDrawerOpen}
        events={events}
        onClose={closeEventDrawer}
        onClear={clearEvents}
      />
    </div>
  );
}
```

- [ ] **Step 3: Delete obsolete components**

```bash
git rm frontend/src/pages/Monitor/DeviceDetailPanel.tsx \
       frontend/src/pages/Monitor/RegisterChart.tsx \
       frontend/src/pages/Monitor/StatsPanel.tsx
```

- [ ] **Step 4: Verify TypeScript build**

```bash
cd frontend && npm run build
```

Expected: PASS (no remaining type errors).

- [ ] **Step 5: Lint**

```bash
cd frontend && npm run lint
```

Expected: PASS (no new lint errors). Fix any introduced errors before committing.

- [ ] **Step 6: Manual smoke (browser)**

Start backend (`cd backend && python -m app.main`) and frontend (`cd frontend && npm run dev`). Open `http://localhost:5173/`.

Verify in this order:
- Redirected to `/monitor`
- Sidebar: Monitor is first item
- With zero devices: EmptyState shown (⚡ icon, "還沒有設備", builtin template chips, "+ 建立設備" button)
- Create one device via `/devices` then return to `/monitor`: card appears, status dot grey (stopped), "▶ Start" link visible
- Click "▶ Start": dot turns green and breathes, primary register value updates each second with cyan flash, sparkline accumulates
- KPI tiles update (Running=1, Stopped=0)
- Click anywhere on the card body: navigates to `/devices/{id}`
- Use Simulation page to inject an anomaly: orange toast appears top-right, fades after 3s, KPI Row 2 shows "1 active anomaly"
- Click 📋 Events button: drawer opens with event list
- Click toast: drawer opens
- Stop the device from `/devices`: card stays visible, fades to ~55% opacity, "▶ Start" reappears

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/Monitor/index.tsx frontend/src/pages/Monitor/DeviceCardGrid.tsx
git commit -m "feat(monitor): rewrite MonitorPage with new components and remove old detail panel (issue #29)"
```

---

## Task 12: Update Playwright e2e and project docs

**Files:**
- Modify: `frontend/e2e/smoke.spec.ts`
- Modify: `CHANGELOG.md`
- Modify: `docs/development-log.md`
- Modify: `docs/development-phases.md`
- Modify: `docs/api-reference.md` (only if WebSocket payload doc exists)

- [ ] **Step 1: Update root smoke test**

Edit `frontend/e2e/smoke.spec.ts`. Replace the `Monitor page loads` test and add a new root-redirect test:

```typescript
  test("Root redirects to Monitor", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveURL(/\/monitor$/);
    await expect(page.locator("text=Monitor").first()).toBeVisible();
  });

  test("Monitor page loads", async ({ page }) => {
    await page.goto("/monitor");
    await expect(page.locator("text=Monitor").first()).toBeVisible();
    // Either EmptyState or KPI tiles must render
    const empty = page.locator("text=還沒有設備");
    const kpi = page.locator("text=Running");
    await expect(empty.or(kpi).first()).toBeVisible();
  });
```

- [ ] **Step 2: Run e2e (if backend + frontend can be reached)**

```bash
cd frontend && npm run test:e2e -- --grep "Monitor|Root redirects"
```

Expected: PASS. If Playwright requires explicit baseURL/server start, run the full suite per project convention. If e2e infra is broken in this environment, document the failure and continue — manual smoke (Task 11 Step 6) is the authoritative check.

- [ ] **Step 3: Update CHANGELOG.md**

Append under `## [Unreleased]`:

```markdown
### Added
- Monitor 首頁重做：卡片網格 + KPI panel + sparkline + 即時值動畫 + Event toast/drawer (issue #29)
- 完全沒設備時的引導空狀態（內建模板捷徑）
- WebSocket monitor_update payload 新增 `mqtt_broker_connected` 欄位
- DeviceMonitorData 新增 `mqtt_stats` 欄位（後端原本已有，前端型別補齊）

### Changed
- `/` route 改導向 `/monitor`（原 `/templates`）
- 側邊欄 Monitor 移到第一位
- Monitor service 不再 filter 掉 stopped 設備（卡片網格會淡化顯示）
- DeviceCard 點擊行為改為跳轉 `/devices/{id}`（取代同頁展開 detail panel）

### Removed
- `pages/Monitor/DeviceDetailPanel.tsx`、`RegisterChart.tsx`、`StatsPanel.tsx`
- monitorStore 的 `selectedDeviceId` / `selectDevice`
```

- [ ] **Step 4: Update `docs/development-log.md`**

Append a new dated section (use today's date):

```markdown
## 2026-04-17 — Monitor 首頁重做 (issue #29)

### 做了什麼
- 把 `/monitor` 從「卡片 + 點擊展開細節 + 底部 Event log」改成「KPI panel + 卡片網格（點擊跳細節頁） + Toast/Drawer」
- 設為全站首頁、側邊欄第一順位
- 加入 4 主 KPI（Running/Stopped/Errors/DPS）+ 條件式 pills（active anomalies/faults、MQTT broker）
- 卡片包含：mid 密度（主指標大字 + sparkline + 副指標小字）、狀態燈動畫（running 呼吸/error 閃爍）、即時值更新 cyan glow flash、hover 上浮、stopped 淡化 + Start 快捷
- Event 觸發 toast 通知（3 秒自動消失）+ Drawer 累積歷史
- 完全空狀態引導（內建模板 chips + 建立 CTA）
- 後端：移除 monitor snapshot 的 stopped filter；新增 `mqtt_broker_connected` top-level 欄位

### 為什麼
- 對應 Phase UI #2（issue #29）— 把 Monitor 升級為視覺焦點
- 解決 stopped 設備不可見導致使用者不知設備存在的問題
- 把 register 細節分析職責還給 `/devices/{id}` 頁，Monitor 專心做 dashboard

### 遇到的問題
- (執行時填寫)
```

- [ ] **Step 5: Update `docs/development-phases.md`**

Mark UI #2 as Complete. Locate the section listing UI #1/#2/#3 status and update UI #2 to "✅ Complete (2026-04-17)". If next phase planning exists, update it accordingly.

- [ ] **Step 6: Update `docs/api-reference.md` (only if it documents the WebSocket payload)**

```bash
grep -n "monitor_update\|/ws/monitor" docs/api-reference.md
```

If matches found: add `mqtt_broker_connected: boolean` to the `monitor_update` payload schema and add `mqtt_stats: MqttStats | null` to the device entry. If no matches, skip this step (no API change to document).

- [ ] **Step 7: Final lint + build sanity**

```bash
cd frontend && npm run lint && npm run build
cd ../backend && pytest -q
```

Expected: all green.

- [ ] **Step 8: Commit docs**

```bash
git add CHANGELOG.md docs/development-log.md docs/development-phases.md docs/api-reference.md frontend/e2e/smoke.spec.ts
git commit -m "docs(monitor): update changelog, dev log, phases, api ref for issue #29"
```

- [ ] **Step 9: Push and open PR**

```bash
git push -u origin feature/claude-monitor-redesign-20260417
gh pr create --title "feat(monitor): redesign Monitor as glance dashboard home (issue #29)" --body "$(cat <<'EOF'
## Summary
- Rebuild `/monitor` as glance dashboard with KPI panel, mid-density device cards, sparklines, value-flash animation, status dot pulse, Event toast/drawer
- Make `/monitor` the home route; move Monitor to top of sidebar
- Surface stopped devices in the grid (faded + Start shortcut); guided empty state when no devices exist
- Backend: include stopped devices in monitor snapshot; expose `mqtt_broker_connected`

Closes #29.

## Test plan
- [ ] `cd backend && pytest -q` — all green
- [ ] `cd frontend && npm run build && npm run lint` — all green
- [ ] `cd frontend && npm run test:e2e -- --grep "Monitor|Root"` — passes
- [ ] Manual: empty state renders with template chips when zero devices
- [ ] Manual: stopped device card faded + Start works
- [ ] Manual: running device — value flash, sparkline accumulates, KPI updates
- [ ] Manual: anomaly inject → orange toast → drawer accumulates
- [ ] Manual: click card → navigates to /devices/{id}

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Return the PR URL.

---

## Self-Review Checklist (run after implementation, before merge)

- [ ] All tasks 1–12 completed and committed
- [ ] `pytest -q` (backend) all green
- [ ] `npm run build` and `npm run lint` (frontend) clean
- [ ] Playwright Monitor smoke passes
- [ ] Manual checklist in Task 11 Step 6 confirmed
- [ ] CHANGELOG / dev log / phases / api-reference updated
- [ ] PR opened with link
