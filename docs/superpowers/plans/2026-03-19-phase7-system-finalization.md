# Phase 7: System Finalization Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finalize GhostMeter MVP with config export/import, Docker optimization, CI pipeline, smoke tests, and v0.1.0 release.

**Architecture:** Adds a system service layer for full-snapshot export/import (templates + devices + simulation configs + anomaly schedules). Docker and CI are infrastructure-only changes. Frontend gets a Settings page with export/import buttons.

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy 2.0 / PostgreSQL 16 / React 18 / TypeScript / Ant Design 5 / Playwright / GitHub Actions

---

## Chunk 1: Config Export/Import Backend

### Task 1: System Export/Import Pydantic Schemas

**Files:**
- Create: `backend/app/schemas/system.py`

- [ ] **Step 1: Create schema file with export/import types**

```python
"""Pydantic schemas for system config export/import."""

from typing import Any

from pydantic import BaseModel, field_validator


class RegisterExport(BaseModel):
    """Register definition in export format (no IDs)."""

    name: str
    address: int
    function_code: int
    data_type: str
    byte_order: str
    scale_factor: float
    unit: str | None = None
    description: str | None = None
    sort_order: int = 0


class TemplateExport(BaseModel):
    """Template in export format (no IDs)."""

    name: str
    protocol: str
    description: str | None = None
    is_builtin: bool
    registers: list[RegisterExport]


class DeviceExport(BaseModel):
    """Device instance in export format (references template by name)."""

    name: str
    template_name: str
    slave_id: int
    port: int = 502
    description: str | None = None


class SimulationConfigExport(BaseModel):
    """Simulation config in export format (references device by name)."""

    device_name: str
    register_name: str
    data_mode: str
    mode_params: dict[str, Any] = {}
    is_enabled: bool = True
    update_interval_ms: int = 1000


class AnomalyScheduleExport(BaseModel):
    """Anomaly schedule in export format (references device by name)."""

    device_name: str
    register_name: str
    anomaly_type: str
    anomaly_params: dict[str, Any] = {}
    trigger_after_seconds: int
    duration_seconds: int
    is_enabled: bool = True


class SystemExport(BaseModel):
    """Full system snapshot for export."""

    version: str = "1.0"
    exported_at: str
    templates: list[TemplateExport]
    devices: list[DeviceExport]
    simulation_configs: list[SimulationConfigExport]
    anomaly_schedules: list[AnomalyScheduleExport]


class SystemImport(BaseModel):
    """Full system snapshot for import."""

    version: str
    templates: list[TemplateExport] = []
    devices: list[DeviceExport] = []
    simulation_configs: list[SimulationConfigExport] = []
    anomaly_schedules: list[AnomalyScheduleExport] = []

    @field_validator("version")
    @classmethod
    def validate_version(cls, v: str) -> str:
        if v != "1.0":
            raise ValueError(f"Unsupported export version '{v}'. Only '1.0' is supported.")
        return v


class ImportResult(BaseModel):
    """Result summary of an import operation."""

    templates_created: int = 0
    templates_updated: int = 0
    templates_skipped: int = 0
    devices_created: int = 0
    devices_updated: int = 0
    simulation_configs_set: int = 0
    anomaly_schedules_set: int = 0
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/schemas/system.py
git commit -m "feat: add system export/import Pydantic schemas"
```

---

### Task 2: System Export Service

**Files:**
- Create: `backend/app/services/system_service.py`
- Test: `backend/tests/test_system_export_import.py`

- [ ] **Step 1: Write failing test for export**

Create `backend/tests/test_system_export_import.py`:

```python
"""Tests for system config export/import."""

from httpx import AsyncClient

TEMPLATE_PAYLOAD = {
    "name": "Export Test Meter",
    "protocol": "modbus_tcp",
    "description": "For export testing",
    "registers": [
        {
            "name": "voltage",
            "address": 0,
            "function_code": 4,
            "data_type": "float32",
            "byte_order": "big_endian",
            "scale_factor": 1.0,
            "unit": "V",
            "description": "Voltage",
            "sort_order": 0,
        },
    ],
}


async def _create_template(client: AsyncClient, payload: dict | None = None) -> dict:
    """Helper: create a template."""
    resp = await client.post("/api/v1/templates", json=payload or TEMPLATE_PAYLOAD)
    assert resp.status_code == 201
    return resp.json()["data"]


async def _create_device(
    client: AsyncClient, template_id: str, name: str = "Dev-01", slave_id: int = 1
) -> dict:
    """Helper: create a device."""
    resp = await client.post(
        "/api/v1/devices",
        json={
            "name": name,
            "template_id": template_id,
            "slave_id": slave_id,
            "port": 502,
        },
    )
    assert resp.status_code == 201
    return resp.json()["data"]


class TestSystemExport:
    async def test_export_empty_system(self, client: AsyncClient) -> None:
        """Export with no user data returns only built-in templates."""
        resp = await client.get("/api/v1/system/export")
        assert resp.status_code == 200
        assert "attachment" in resp.headers.get("content-disposition", "")
        data = resp.json()
        assert data["version"] == "1.0"
        assert "exported_at" in data
        # Built-in templates are included (if seeded)
        assert isinstance(data["templates"], list)
        assert data["devices"] == []
        assert data["simulation_configs"] == []
        assert data["anomaly_schedules"] == []

    async def test_export_with_template_and_device(self, client: AsyncClient) -> None:
        """Export includes user-created templates and devices."""
        template = await _create_template(client)
        await _create_device(client, template["id"])

        resp = await client.get("/api/v1/system/export")
        assert resp.status_code == 200
        data = resp.json()

        # Find our template in export
        names = [t["name"] for t in data["templates"]]
        assert "Export Test Meter" in names

        # Device references template by name
        assert len(data["devices"]) == 1
        assert data["devices"][0]["template_name"] == "Export Test Meter"
        assert data["devices"][0]["slave_id"] == 1

        # No IDs in export
        for t in data["templates"]:
            assert "id" not in t
        for d in data["devices"]:
            assert "id" not in d
            assert "template_id" not in d

    async def test_export_includes_simulation_configs(self, client: AsyncClient) -> None:
        """Export includes simulation configs referencing device by name."""
        template = await _create_template(client)
        device = await _create_device(client, template["id"])

        # Set simulation config
        await client.put(
            f"/api/v1/devices/{device['id']}/simulation",
            json={
                "configs": [
                    {
                        "register_name": "voltage",
                        "data_mode": "static",
                        "mode_params": {"value": 230.0},
                        "is_enabled": True,
                        "update_interval_ms": 1000,
                    }
                ]
            },
        )

        resp = await client.get("/api/v1/system/export")
        data = resp.json()
        assert len(data["simulation_configs"]) == 1
        assert data["simulation_configs"][0]["device_name"] == "Dev-01"
        assert data["simulation_configs"][0]["register_name"] == "voltage"

    async def test_export_includes_anomaly_schedules(self, client: AsyncClient) -> None:
        """Export includes anomaly schedules referencing device by name."""
        template = await _create_template(client)
        device = await _create_device(client, template["id"])

        # Set anomaly schedule
        await client.put(
            f"/api/v1/devices/{device['id']}/anomaly/schedules",
            json={
                "schedules": [
                    {
                        "register_name": "voltage",
                        "anomaly_type": "spike",
                        "anomaly_params": {"multiplier": 3.0, "probability": 0.1},
                        "trigger_after_seconds": 60,
                        "duration_seconds": 30,
                        "is_enabled": True,
                    }
                ]
            },
        )

        resp = await client.get("/api/v1/system/export")
        data = resp.json()
        assert len(data["anomaly_schedules"]) == 1
        assert data["anomaly_schedules"][0]["device_name"] == "Dev-01"
        assert data["anomaly_schedules"][0]["anomaly_type"] == "spike"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest backend/tests/test_system_export_import.py -v`
Expected: FAIL — 404 on `/api/v1/system/export`

- [ ] **Step 3: Implement system_service.py export function**

Create `backend/app/services/system_service.py`:

```python
"""System-level service for config export/import."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.anomaly import AnomalySchedule
from app.models.device import DeviceInstance
from app.models.simulation import SimulationConfig
from app.models.template import DeviceTemplate
from app.schemas.system import (
    AnomalyScheduleExport,
    DeviceExport,
    ImportResult,
    RegisterExport,
    SimulationConfigExport,
    SystemExport,
    TemplateExport,
)


async def export_system(session: AsyncSession) -> SystemExport:
    """Export full system config as a snapshot."""
    # Templates with registers
    stmt = select(DeviceTemplate).options(selectinload(DeviceTemplate.registers))
    result = await session.execute(stmt)
    templates = result.scalars().all()

    template_exports = []
    for t in templates:
        template_exports.append(
            TemplateExport(
                name=t.name,
                protocol=t.protocol,
                description=t.description,
                is_builtin=t.is_builtin,
                registers=[
                    RegisterExport(
                        name=r.name,
                        address=r.address,
                        function_code=r.function_code,
                        data_type=r.data_type,
                        byte_order=r.byte_order,
                        scale_factor=r.scale_factor,
                        unit=r.unit,
                        description=r.description,
                        sort_order=r.sort_order,
                    )
                    for r in t.registers
                ],
            )
        )

    # Devices — build id→name map for later use
    stmt = (
        select(DeviceInstance, DeviceTemplate.name)
        .join(DeviceTemplate, DeviceInstance.template_id == DeviceTemplate.id)
    )
    result = await session.execute(stmt)
    rows = result.all()

    device_id_to_name: dict[uuid.UUID, str] = {}
    device_exports = []
    for device, template_name in rows:
        device_id_to_name[device.id] = device.name
        device_exports.append(
            DeviceExport(
                name=device.name,
                template_name=template_name,
                slave_id=device.slave_id,
                port=device.port,
                description=device.description,
            )
        )

    # Simulation configs
    stmt = select(SimulationConfig)
    result = await session.execute(stmt)
    sim_configs = result.scalars().all()

    sim_exports = []
    for sc in sim_configs:
        device_name = device_id_to_name.get(sc.device_id)
        if device_name is None:
            continue
        sim_exports.append(
            SimulationConfigExport(
                device_name=device_name,
                register_name=sc.register_name,
                data_mode=sc.data_mode,
                mode_params=sc.mode_params,
                is_enabled=sc.is_enabled,
                update_interval_ms=sc.update_interval_ms,
            )
        )

    # Anomaly schedules
    stmt = select(AnomalySchedule)
    result = await session.execute(stmt)
    schedules = result.scalars().all()

    schedule_exports = []
    for s in schedules:
        device_name = device_id_to_name.get(s.device_id)
        if device_name is None:
            continue
        schedule_exports.append(
            AnomalyScheduleExport(
                device_name=device_name,
                register_name=s.register_name,
                anomaly_type=s.anomaly_type,
                anomaly_params=s.anomaly_params,
                trigger_after_seconds=s.trigger_after_seconds,
                duration_seconds=s.duration_seconds,
                is_enabled=s.is_enabled,
            )
        )

    return SystemExport(
        version="1.0",
        exported_at=datetime.now(UTC).isoformat(),
        templates=template_exports,
        devices=device_exports,
        simulation_configs=sim_exports,
        anomaly_schedules=schedule_exports,
    )
```

- [ ] **Step 4: Create system routes**

Create `backend/app/api/routes/system.py`:

```python
"""System-level API routes for config export/import."""

import json

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas.common import ApiResponse
from app.schemas.system import SystemImport, ImportResult
from app.services import system_service

router = APIRouter()


@router.get("/export")
async def export_config(session: AsyncSession = Depends(get_session)) -> Response:
    """Export full system configuration as JSON file download."""
    snapshot = await system_service.export_system(session)
    content = json.dumps(snapshot.model_dump(), indent=2, ensure_ascii=False)
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=ghostmeter-config.json"},
    )
```

- [ ] **Step 5: Register system router in main.py**

In `backend/app/main.py`, add:

```python
from app.api.routes.system import router as system_router
# ... in the api_v1_router section:
api_v1_router.include_router(system_router, prefix="/system", tags=["system"])
```

- [ ] **Step 6: Run export tests**

Run: `pytest backend/tests/test_system_export_import.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/system_service.py backend/app/api/routes/system.py backend/app/main.py backend/app/schemas/system.py backend/tests/test_system_export_import.py
git commit -m "feat: add system config export API with full snapshot"
```

---

### Task 3: System Import Service

**Files:**
- Modify: `backend/app/services/system_service.py`
- Modify: `backend/app/api/routes/system.py`
- Test: `backend/tests/test_system_export_import.py`

- [ ] **Step 1: Write failing tests for import**

Add to `backend/tests/test_system_export_import.py`:

```python
class TestSystemImport:
    async def test_import_empty_payload(self, client: AsyncClient) -> None:
        """Import with no data returns zero counts."""
        resp = await client.post(
            "/api/v1/system/import",
            json={"version": "1.0", "templates": [], "devices": []},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["templates_created"] == 0
        assert data["devices_created"] == 0

    async def test_import_invalid_version(self, client: AsyncClient) -> None:
        """Import with unsupported version returns 422."""
        resp = await client.post(
            "/api/v1/system/import",
            json={"version": "99.0", "templates": []},
        )
        assert resp.status_code == 422

    async def test_import_template(self, client: AsyncClient) -> None:
        """Import creates a new template."""
        payload = {
            "version": "1.0",
            "templates": [
                {
                    "name": "Imported Meter",
                    "protocol": "modbus_tcp",
                    "description": "Imported",
                    "is_builtin": False,
                    "registers": [
                        {
                            "name": "voltage",
                            "address": 0,
                            "function_code": 4,
                            "data_type": "float32",
                            "byte_order": "big_endian",
                            "scale_factor": 1.0,
                            "unit": "V",
                            "sort_order": 0,
                        }
                    ],
                }
            ],
        }
        resp = await client.post("/api/v1/system/import", json=payload)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["templates_created"] == 1

        # Verify template exists
        resp = await client.get("/api/v1/templates")
        names = [t["name"] for t in resp.json()["data"]]
        assert "Imported Meter" in names

    async def test_import_skips_builtin_templates(self, client: AsyncClient) -> None:
        """Import skips templates marked as built-in."""
        payload = {
            "version": "1.0",
            "templates": [
                {
                    "name": "Should Be Skipped",
                    "protocol": "modbus_tcp",
                    "is_builtin": True,
                    "registers": [
                        {
                            "name": "v",
                            "address": 0,
                            "function_code": 4,
                            "data_type": "float32",
                            "byte_order": "big_endian",
                            "scale_factor": 1.0,
                            "sort_order": 0,
                        }
                    ],
                }
            ],
        }
        resp = await client.post("/api/v1/system/import", json=payload)
        data = resp.json()["data"]
        assert data["templates_skipped"] == 1
        assert data["templates_created"] == 0

    async def test_import_device_with_template(self, client: AsyncClient) -> None:
        """Import creates template and device together."""
        payload = {
            "version": "1.0",
            "templates": [
                {
                    "name": "Import Template",
                    "protocol": "modbus_tcp",
                    "is_builtin": False,
                    "registers": [
                        {
                            "name": "voltage",
                            "address": 0,
                            "function_code": 4,
                            "data_type": "float32",
                            "byte_order": "big_endian",
                            "scale_factor": 1.0,
                            "sort_order": 0,
                        }
                    ],
                }
            ],
            "devices": [
                {
                    "name": "Import Device",
                    "template_name": "Import Template",
                    "slave_id": 10,
                    "port": 502,
                }
            ],
        }
        resp = await client.post("/api/v1/system/import", json=payload)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["templates_created"] == 1
        assert data["devices_created"] == 1

    async def test_import_device_unknown_template_fails(self, client: AsyncClient) -> None:
        """Import fails if device references nonexistent template."""
        payload = {
            "version": "1.0",
            "devices": [
                {
                    "name": "Orphan Device",
                    "template_name": "NonexistentTemplate",
                    "slave_id": 99,
                    "port": 502,
                }
            ],
        }
        resp = await client.post("/api/v1/system/import", json=payload)
        assert resp.status_code == 422

    async def test_import_simulation_configs(self, client: AsyncClient) -> None:
        """Import creates simulation configs for devices."""
        payload = {
            "version": "1.0",
            "templates": [
                {
                    "name": "SimTemplate",
                    "protocol": "modbus_tcp",
                    "is_builtin": False,
                    "registers": [
                        {
                            "name": "voltage",
                            "address": 0,
                            "function_code": 4,
                            "data_type": "float32",
                            "byte_order": "big_endian",
                            "scale_factor": 1.0,
                            "sort_order": 0,
                        }
                    ],
                }
            ],
            "devices": [
                {
                    "name": "SimDevice",
                    "template_name": "SimTemplate",
                    "slave_id": 20,
                    "port": 502,
                }
            ],
            "simulation_configs": [
                {
                    "device_name": "SimDevice",
                    "register_name": "voltage",
                    "data_mode": "static",
                    "mode_params": {"value": 230.0},
                    "is_enabled": True,
                    "update_interval_ms": 1000,
                }
            ],
        }
        resp = await client.post("/api/v1/system/import", json=payload)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["simulation_configs_set"] == 1

    async def test_roundtrip_export_import(self, client: AsyncClient) -> None:
        """Export then import produces identical system state."""
        # Create template + device + simulation config
        template = await _create_template(client)
        device = await _create_device(client, template["id"])
        await client.put(
            f"/api/v1/devices/{device['id']}/simulation",
            json={
                "configs": [
                    {
                        "register_name": "voltage",
                        "data_mode": "random",
                        "mode_params": {"base": 230.0, "amplitude": 5.0},
                        "is_enabled": True,
                        "update_interval_ms": 500,
                    }
                ]
            },
        )

        # Export
        resp = await client.get("/api/v1/system/export")
        export_data = resp.json()

        # Delete everything (device first due to FK)
        await client.delete(f"/api/v1/devices/{device['id']}")
        await client.delete(f"/api/v1/templates/{template['id']}")

        # Import back
        resp = await client.post("/api/v1/system/import", json=export_data)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["templates_created"] >= 1
        assert data["devices_created"] == 1
        assert data["simulation_configs_set"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest backend/tests/test_system_export_import.py::TestSystemImport -v`
Expected: FAIL — 405 or 404 on POST `/api/v1/system/import`

- [ ] **Step 3: Implement import_system in system_service.py**

Add to `backend/app/services/system_service.py`:

```python
from sqlalchemy import delete

from app.exceptions import ValidationException
from app.models.template import RegisterDefinition
from app.schemas.system import SystemImport


async def import_system(session: AsyncSession, data: SystemImport) -> ImportResult:
    """Import full system config from a snapshot. All-or-nothing transaction."""
    result = ImportResult()

    # Step 1: Import templates
    template_name_to_id: dict[str, uuid.UUID] = {}

    # Load existing templates for upsert lookup
    stmt = select(DeviceTemplate).options(selectinload(DeviceTemplate.registers))
    existing = await session.execute(stmt)
    existing_templates = {t.name: t for t in existing.scalars().all()}

    for t_export in data.templates:
        if t_export.is_builtin:
            result.templates_skipped += 1
            # Still map the name→id for device resolution
            if t_export.name in existing_templates:
                template_name_to_id[t_export.name] = existing_templates[t_export.name].id
            continue

        if t_export.name in existing_templates:
            # Update existing template
            existing_t = existing_templates[t_export.name]
            existing_t.protocol = t_export.protocol
            existing_t.description = t_export.description

            # Replace registers: delete old, add new
            await session.execute(
                delete(RegisterDefinition).where(
                    RegisterDefinition.template_id == existing_t.id
                )
            )
            for r in t_export.registers:
                session.add(
                    RegisterDefinition(
                        template_id=existing_t.id,
                        name=r.name,
                        address=r.address,
                        function_code=r.function_code,
                        data_type=r.data_type,
                        byte_order=r.byte_order,
                        scale_factor=r.scale_factor,
                        unit=r.unit,
                        description=r.description,
                        sort_order=r.sort_order,
                    )
                )
            template_name_to_id[t_export.name] = existing_t.id
            result.templates_updated += 1
        else:
            # Create new template
            new_t = DeviceTemplate(
                name=t_export.name,
                protocol=t_export.protocol,
                description=t_export.description,
                is_builtin=False,
            )
            session.add(new_t)
            await session.flush()  # Get the ID

            for r in t_export.registers:
                session.add(
                    RegisterDefinition(
                        template_id=new_t.id,
                        name=r.name,
                        address=r.address,
                        function_code=r.function_code,
                        data_type=r.data_type,
                        byte_order=r.byte_order,
                        scale_factor=r.scale_factor,
                        unit=r.unit,
                        description=r.description,
                        sort_order=r.sort_order,
                    )
                )
            template_name_to_id[t_export.name] = new_t.id
            result.templates_created += 1

    # Also map existing built-in templates not in export
    for name, t in existing_templates.items():
        if name not in template_name_to_id:
            template_name_to_id[name] = t.id

    await session.flush()

    # Step 2: Import devices
    device_name_to_id: dict[str, uuid.UUID] = {}

    # Load existing devices for upsert lookup
    stmt = select(DeviceInstance)
    existing = await session.execute(stmt)
    existing_devices = {(d.slave_id, d.port): d for d in existing.scalars().all()}

    for d_export in data.devices:
        template_id = template_name_to_id.get(d_export.template_name)
        if template_id is None:
            raise ValidationException(
                detail=f"Device '{d_export.name}' references unknown template "
                f"'{d_export.template_name}'"
            )

        key = (d_export.slave_id, d_export.port)
        if key in existing_devices:
            # Update existing device
            existing_d = existing_devices[key]
            existing_d.name = d_export.name
            existing_d.template_id = template_id
            existing_d.description = d_export.description
            if existing_d.status == "running":
                existing_d.status = "stopped"
            device_name_to_id[d_export.name] = existing_d.id
            result.devices_updated += 1
        else:
            # Create new device
            new_d = DeviceInstance(
                name=d_export.name,
                template_id=template_id,
                slave_id=d_export.slave_id,
                port=d_export.port,
                description=d_export.description,
                status="stopped",
            )
            session.add(new_d)
            await session.flush()
            device_name_to_id[d_export.name] = new_d.id
            result.devices_created += 1

    await session.flush()

    # Also map existing devices not in import
    for key, d in existing_devices.items():
        if d.name not in device_name_to_id:
            device_name_to_id[d.name] = d.id

    # Step 3: Import simulation configs (delete once per device, then insert all)
    sim_devices_cleared: set[str] = set()
    for sc_export in data.simulation_configs:
        device_id = device_name_to_id.get(sc_export.device_name)
        if device_id is None:
            continue

        if sc_export.device_name not in sim_devices_cleared:
            await session.execute(
                delete(SimulationConfig).where(SimulationConfig.device_id == device_id)
            )
            sim_devices_cleared.add(sc_export.device_name)

        session.add(
            SimulationConfig(
                device_id=device_id,
                register_name=sc_export.register_name,
                data_mode=sc_export.data_mode,
                mode_params=sc_export.mode_params,
                is_enabled=sc_export.is_enabled,
                update_interval_ms=sc_export.update_interval_ms,
            )
        )
        result.simulation_configs_set += 1

    # Step 4: Import anomaly schedules
    sched_devices_cleared: set[str] = set()
    for s_export in data.anomaly_schedules:
        device_id = device_name_to_id.get(s_export.device_name)
        if device_id is None:
            continue

        if s_export.device_name not in sched_devices_cleared:
            await session.execute(
                delete(AnomalySchedule).where(AnomalySchedule.device_id == device_id)
            )
            sched_devices_cleared.add(s_export.device_name)

        session.add(
            AnomalySchedule(
                device_id=device_id,
                register_name=s_export.register_name,
                anomaly_type=s_export.anomaly_type,
                anomaly_params=s_export.anomaly_params,
                trigger_after_seconds=s_export.trigger_after_seconds,
                duration_seconds=s_export.duration_seconds,
                is_enabled=s_export.is_enabled,
            )
        )
        result.anomaly_schedules_set += 1

    await session.commit()
    return result
```

- [ ] **Step 4: Add import route**

Add to `backend/app/api/routes/system.py`:

```python
@router.post("/import", response_model=ApiResponse[ImportResult])
async def import_config(
    data: SystemImport,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[ImportResult]:
    """Import system configuration from JSON snapshot."""
    result = await system_service.import_system(session, data)
    return ApiResponse(data=result, message="Import completed successfully")
```

- [ ] **Step 5: Run all import tests**

Run: `pytest backend/tests/test_system_export_import.py -v`
Expected: PASS (all export + import tests)

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/system_service.py backend/app/api/routes/system.py backend/tests/test_system_export_import.py
git commit -m "feat: add system config import API with upsert logic"
```

---

## Chunk 2: Frontend Settings Page + Docker/CI

### Task 4: Frontend Settings Page

**Files:**
- Create: `frontend/src/services/systemApi.ts`
- Create: `frontend/src/pages/Settings/index.tsx`
- Modify: `frontend/src/App.tsx` — add `/settings` route
- Modify: `frontend/src/layouts/MainLayout.tsx` — add Settings menu item
- Modify: `frontend/src/types/index.ts` — add system types

- [ ] **Step 1: Add system types**

Add to `frontend/src/types/index.ts`:

```typescript
export type { ImportResult, SystemExport } from "./system";
```

Create `frontend/src/types/system.ts`:

```typescript
export interface ImportResult {
  templates_created: number;
  templates_updated: number;
  templates_skipped: number;
  devices_created: number;
  devices_updated: number;
  simulation_configs_set: number;
  anomaly_schedules_set: number;
}

export interface SystemExport {
  version: string;
  exported_at: string;
  templates: unknown[];
  devices: unknown[];
  simulation_configs: unknown[];
  anomaly_schedules: unknown[];
}
```

- [ ] **Step 2: Create systemApi.ts**

Create `frontend/src/services/systemApi.ts`:

```typescript
import { api } from "./api";
import type { ApiResponse, ImportResult } from "../types";

export const systemApi = {
  exportConfig: () =>
    api.get<Record<string, unknown>>("/system/export").then((r) => r.data),

  importConfig: (data: Record<string, unknown>) =>
    api.post<ApiResponse<ImportResult>>("/system/import", data).then((r) => r.data),
};
```

- [ ] **Step 3: Create Settings page**

Create `frontend/src/pages/Settings/index.tsx`:

```tsx
import { DownloadOutlined, UploadOutlined } from "@ant-design/icons";
import { Button, Card, message, Modal, Space, Typography, Upload } from "antd";
import type { UploadProps } from "antd";
import { useState } from "react";
import { systemApi } from "../../services/systemApi";
import type { ImportResult } from "../../types";

export default function SettingsPage() {
  const [importing, setImporting] = useState(false);
  const [exporting, setExporting] = useState(false);

  const handleExport = async () => {
    setExporting(true);
    try {
      const data = await systemApi.exportConfig();
      const blob = new Blob([JSON.stringify(data, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `ghostmeter-config-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
      message.success("Configuration exported successfully");
    } catch {
      message.error("Export failed");
    } finally {
      setExporting(false);
    }
  };

  const formatResult = (result: ImportResult): string => {
    const lines: string[] = [];
    if (result.templates_created > 0) lines.push(`Templates created: ${result.templates_created}`);
    if (result.templates_updated > 0) lines.push(`Templates updated: ${result.templates_updated}`);
    if (result.templates_skipped > 0) lines.push(`Templates skipped: ${result.templates_skipped}`);
    if (result.devices_created > 0) lines.push(`Devices created: ${result.devices_created}`);
    if (result.devices_updated > 0) lines.push(`Devices updated: ${result.devices_updated}`);
    if (result.simulation_configs_set > 0) lines.push(`Simulation configs: ${result.simulation_configs_set}`);
    if (result.anomaly_schedules_set > 0) lines.push(`Anomaly schedules: ${result.anomaly_schedules_set}`);
    return lines.length > 0 ? lines.join("\n") : "No changes made";
  };

  const uploadProps: UploadProps = {
    accept: ".json",
    showUploadList: false,
    beforeUpload: async (file) => {
      setImporting(true);
      try {
        const text = await file.text();
        const data = JSON.parse(text);
        const resp = await systemApi.importConfig(data);
        if (resp.data) {
          Modal.success({
            title: "Import Complete",
            content: formatResult(resp.data),
            style: { whiteSpace: "pre-line" },
          });
        }
      } catch {
        message.error("Import failed — check file format");
      } finally {
        setImporting(false);
      }
      return false; // Prevent default upload behavior
    },
  };

  return (
    <div>
      <Typography.Title level={2}>Settings</Typography.Title>
      <Card title="Configuration Management" style={{ maxWidth: 600 }}>
        <Typography.Paragraph>
          Export your full system configuration (templates, devices, simulation
          configs, anomaly schedules) as a JSON file. Import to restore or
          migrate to another instance.
        </Typography.Paragraph>
        <Space>
          <Button
            type="primary"
            icon={<DownloadOutlined />}
            onClick={handleExport}
            loading={exporting}
          >
            Export Config
          </Button>
          <Upload {...uploadProps}>
            <Button icon={<UploadOutlined />} loading={importing}>
              Import Config
            </Button>
          </Upload>
        </Space>
      </Card>
    </div>
  );
}
```

- [ ] **Step 4: Add route and menu item**

In `frontend/src/App.tsx`, add:

```typescript
import SettingsPage from "./pages/Settings";
// ... in Routes:
<Route path="/settings" element={<SettingsPage />} />
```

In `frontend/src/layouts/MainLayout.tsx`, add to imports:

```typescript
import { SettingOutlined } from "@ant-design/icons";
```

Add to `menuItems` array:

```typescript
{ key: "/settings", icon: <SettingOutlined />, label: "Settings" },
```

- [ ] **Step 5: Verify frontend builds**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: No errors

- [ ] **Step 6: Commit**

```bash
git add frontend/src/types/system.ts frontend/src/types/index.ts frontend/src/services/systemApi.ts frontend/src/pages/Settings/index.tsx frontend/src/App.tsx frontend/src/layouts/MainLayout.tsx
git commit -m "feat: add Settings page with config export/import UI"
```

---

### Task 5: Docker Optimization

**Files:**
- Modify: `backend/Dockerfile`
- Create: `backend/.dockerignore`
- Create: `frontend/.dockerignore`

- [ ] **Step 1: Update backend Dockerfile**

Replace `backend/Dockerfile`:

```dockerfile
FROM python:3.12-slim AS base
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

(Keep it simple — the current Dockerfile is already close to optimal. The main improvement is adding `.dockerignore`.)

- [ ] **Step 2: Create backend/.dockerignore**

```
__pycache__
*.pyc
.pytest_cache
tests/
.ruff_cache
*.egg-info
.mypy_cache
```

- [ ] **Step 3: Create frontend/.dockerignore**

```
node_modules
dist
.vite
*.log
```

- [ ] **Step 4: Commit**

```bash
git add backend/.dockerignore frontend/.dockerignore
git commit -m "chore: add .dockerignore files to reduce build context"
```

---

### Task 6: GitHub Actions CI Pipeline

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Create CI workflow**

```yaml
name: CI

on:
  push:
    branches: [dev, main]
  pull_request:
    branches: [dev, main]

jobs:
  backend:
    name: Backend (lint + test)
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: ghostmeter
          POSTGRES_PASSWORD: ghostmeter
          POSTGRES_DB: ghostmeter
        ports:
          - 5432:5432
        options: >-
          --health-cmd "pg_isready -U ghostmeter"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    defaults:
      run:
        working-directory: backend

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python 3.12
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: pip install -r requirements.txt ruff pytest-cov

      - name: Lint with ruff
        run: ruff check .

      - name: Run migrations
        env:
          POSTGRES_HOST: localhost
          POSTGRES_PORT: 5432
          POSTGRES_USER: ghostmeter
          POSTGRES_PASSWORD: ghostmeter
          POSTGRES_DB: ghostmeter
          APP_NAME: GhostMeter
          APP_VERSION: 0.1.0
          MODBUS_HOST: 0.0.0.0
          MODBUS_PORT: 5020
        run: alembic upgrade head

      - name: Run tests
        env:
          POSTGRES_HOST: localhost
          POSTGRES_PORT: 5432
          POSTGRES_USER: ghostmeter
          POSTGRES_PASSWORD: ghostmeter
          POSTGRES_DB: ghostmeter
          APP_NAME: GhostMeter
          APP_VERSION: 0.1.0
          MODBUS_HOST: 0.0.0.0
          MODBUS_PORT: 5020
        run: pytest --cov=app --cov-report=term-missing -v

  frontend:
    name: Frontend (typecheck + build + smoke)
    runs-on: ubuntu-latest

    defaults:
      run:
        working-directory: frontend

    steps:
      - uses: actions/checkout@v4

      - name: Set up Node 20
        uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"
          cache-dependency-path: frontend/package-lock.json

      - name: Install dependencies
        run: npm ci

      - name: Type check
        run: npx tsc --noEmit

      - name: Build
        run: npm run build

      - name: Install Playwright
        run: npx playwright install --with-deps chromium

      - name: Run smoke tests
        run: npx playwright test
```

- [ ] **Step 2: Commit**

```bash
mkdir -p .github/workflows
git add .github/workflows/ci.yml
git commit -m "ci: add GitHub Actions pipeline for backend lint/test and frontend build"
```

---

## Chunk 3: Test Coverage + Docs + Release

### Task 7: Backend Test Coverage Improvement

**Files:**
- Modify: `backend/tests/test_system_export_import.py` (add edge cases)
- May create additional test files as needed

- [ ] **Step 1: Measure current coverage**

Run: `cd backend && pip install pytest-cov && pytest --cov=app --cov-report=term-missing -v`

Review output to identify modules with low coverage.

- [ ] **Step 2: Add edge case tests for export/import**

Add to `backend/tests/test_system_export_import.py`:

```python
class TestSystemImportEdgeCases:
    async def test_import_updates_existing_template(self, client: AsyncClient) -> None:
        """Import updates template if name already exists."""
        # Create template first
        await _create_template(client)

        # Import with same name, different description
        payload = {
            "version": "1.0",
            "templates": [
                {
                    "name": "Export Test Meter",
                    "protocol": "modbus_tcp",
                    "description": "Updated via import",
                    "is_builtin": False,
                    "registers": [
                        {
                            "name": "current",
                            "address": 10,
                            "function_code": 4,
                            "data_type": "float32",
                            "byte_order": "big_endian",
                            "scale_factor": 1.0,
                            "unit": "A",
                            "sort_order": 0,
                        }
                    ],
                }
            ],
        }
        resp = await client.post("/api/v1/system/import", json=payload)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["templates_updated"] == 1
        assert data["templates_created"] == 0

    async def test_import_updates_existing_device(self, client: AsyncClient) -> None:
        """Import updates device if (slave_id, port) already exists."""
        template = await _create_template(client)
        await _create_device(client, template["id"])

        # Import device with same slave_id/port
        payload = {
            "version": "1.0",
            "devices": [
                {
                    "name": "Updated Device",
                    "template_name": "Export Test Meter",
                    "slave_id": 1,
                    "port": 502,
                    "description": "Updated via import",
                }
            ],
        }
        resp = await client.post("/api/v1/system/import", json=payload)
        data = resp.json()["data"]
        assert data["devices_updated"] == 1
        assert data["devices_created"] == 0
```

- [ ] **Step 3: Add tests for any low-coverage modules identified in Step 1**

Focus on service methods and edge cases. Exact tests depend on coverage report.

- [ ] **Step 4: Verify coverage > 70%**

Run: `pytest --cov=app --cov-report=term-missing -v`
Expected: Overall coverage > 70%

- [ ] **Step 5: Commit**

```bash
git add backend/tests/
git commit -m "test: improve backend test coverage for export/import edge cases"
```

---

### Task 8: Frontend Playwright Smoke Tests

**Files:**
- Create: `frontend/playwright.config.ts`
- Create: `frontend/e2e/smoke.spec.ts`
- Modify: `frontend/package.json` — add playwright deps and scripts

- [ ] **Step 1: Install Playwright**

```bash
cd frontend
npm install -D @playwright/test
npx playwright install chromium
```

- [ ] **Step 2: Create Playwright config**

Create `frontend/playwright.config.ts`:

```typescript
import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 30000,
  retries: 0,
  use: {
    baseURL: "http://localhost:4173",
    headless: true,
  },
  webServer: {
    command: "npm run preview",
    port: 4173,
    reuseExistingServer: true,
  },
});
```

- [ ] **Step 3: Create smoke tests**

Create `frontend/e2e/smoke.spec.ts`:

```typescript
import { expect, test } from "@playwright/test";

test.describe("Smoke Tests", () => {
  test("Templates page loads", async ({ page }) => {
    await page.goto("/templates");
    await expect(page.locator("text=Device Templates")).toBeVisible();
  });

  test("Devices page loads", async ({ page }) => {
    await page.goto("/devices");
    await expect(page.locator("text=Device")).toBeVisible();
  });

  test("Simulation page loads", async ({ page }) => {
    await page.goto("/simulation");
    await expect(page.locator("text=Simulation")).toBeVisible();
  });

  test("Monitor page loads", async ({ page }) => {
    await page.goto("/monitor");
    await expect(page.locator("text=Monitor")).toBeVisible();
  });

  test("Settings page loads with export/import buttons", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.locator("text=Settings")).toBeVisible();
    await expect(page.locator("text=Export Config")).toBeVisible();
    await expect(page.locator("text=Import Config")).toBeVisible();
  });
});
```

- [ ] **Step 4: Add npm script**

In `frontend/package.json`, add to `"scripts"`:

```json
"test:e2e": "playwright test"
```

- [ ] **Step 5: Build and run smoke tests**

```bash
cd frontend
npm run build
npx playwright test
```

Expected: 5 tests PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/playwright.config.ts frontend/e2e/smoke.spec.ts frontend/package.json frontend/package-lock.json
git commit -m "test: add Playwright smoke tests for all pages"
```

---

### Task 9: CONTRIBUTING.md

**Files:**
- Create: `CONTRIBUTING.md`

- [ ] **Step 1: Create CONTRIBUTING.md**

```markdown
# Contributing to GhostMeter

Thank you for your interest in contributing to GhostMeter!

## Development Setup

### Prerequisites

- Python 3.12+
- Node.js 20+
- Docker & Docker Compose
- PostgreSQL 16 (or use Docker)

### Getting Started

```bash
# Clone the repo
git clone https://github.com/kencoolguy/GhostMeter.git
cd GhostMeter

# Start PostgreSQL
docker compose up -d postgres

# Backend
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000

# Frontend (in another terminal)
cd frontend
npm install
npm run dev
```

## Branch Naming

- Features: `feature/<description>-YYYYMMDD`
- Bug fixes: `fix/<description>`
- Refactoring: `refactor/<description>`

**Never commit directly to `main` or `dev`.**

## Commit Messages

Use [Conventional Commits](https://www.conventionalcommits.org/):

- `feat:` — new feature
- `fix:` — bug fix
- `docs:` — documentation only
- `test:` — adding/updating tests
- `refactor:` — code change that neither fixes a bug nor adds a feature
- `chore:` — maintenance tasks
- `ci:` — CI/CD changes

## Running Tests

```bash
# Backend
cd backend
pytest -v

# Frontend type check
cd frontend
npx tsc --noEmit

# Frontend E2E
cd frontend
npm run build
npx playwright test
```

## Code Style

### Python (Backend)

- PEP 8, max line length 100
- Type hints on all function signatures
- Google-style docstrings on public functions
- Lint with `ruff check .`

### TypeScript (Frontend)

- Strict mode enabled
- Functional components only
- Named exports (except pages)
- `const` by default

## Pull Requests

1. Create a feature branch from `dev`
2. Make your changes with tests
3. Ensure all tests pass and linting is clean
4. Submit a PR to `dev`
5. Wait for review before merging

## Project Structure

See the main [README.md](README.md) for project structure details.
```

- [ ] **Step 2: Commit**

```bash
git add CONTRIBUTING.md
git commit -m "docs: add CONTRIBUTING.md with development guidelines"
```

---

### Task 10: Update Documentation & Dev Phases

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `docs/development-log.md`
- Modify: `docs/development-phases.md`
- Modify: `docs/api-reference.md`

- [ ] **Step 1: Update CHANGELOG.md**

Add under `## [Unreleased]`:

```markdown
### Added
- System config export/import API (`GET /api/v1/system/export`, `POST /api/v1/system/import`)
- Settings page with export/import UI
- GitHub Actions CI pipeline (backend lint/test + frontend typecheck/build)
- Playwright smoke tests for all frontend pages
- CONTRIBUTING.md
- `.dockerignore` files for backend and frontend
- Ruff lint configuration in `pyproject.toml`
```

- [ ] **Step 2: Update docs/development-log.md**

Add new entry at top for Phase 7 with: what was done, decisions, issues encountered, test results.

- [ ] **Step 3: Update docs/development-phases.md**

Mark all Phase 7 milestone items as `[x]` complete. Update status table row for Phase 7 to `✅`.

- [ ] **Step 4: Update docs/api-reference.md**

Add system export/import endpoints:

```markdown
### System

#### Export Configuration
- **GET** `/api/v1/system/export`
- Response: Full system snapshot JSON

#### Import Configuration
- **POST** `/api/v1/system/import`
- Body: System snapshot JSON (same format as export)
- Response: `ApiResponse<ImportResult>` with counts
```

**Note:** `docs/database-schema.md` — no DB schema changes in Phase 7 (no new tables/migrations), so no update needed.

- [ ] **Step 5: Commit**

```bash
git add CHANGELOG.md docs/development-log.md docs/development-phases.md docs/api-reference.md
git commit -m "docs: update changelog, dev log, phases, and API reference for Phase 7"
```

---

### Task 11: Tag v0.1.0 Release

**Prerequisites:** All previous tasks complete, all tests passing, branch merged to `dev` then to `main`.

- [ ] **Step 1: Run full test suite one final time**

```bash
cd backend && pytest -v
cd ../frontend && npx tsc --noEmit && npm run build
```

Expected: All passing

- [ ] **Step 2: Create PR to dev, then to main**

Follow project git workflow — PR to `dev` first, review, merge, then PR to `main`.

- [ ] **Step 3: Tag release on main**

```bash
git checkout main
git pull
git tag -a v0.1.0 -m "GhostMeter v0.1.0 — MVP Release"
git push origin v0.1.0
```

- [ ] **Step 4: Create GitHub Release**

```bash
gh release create v0.1.0 --title "GhostMeter v0.1.0 — MVP" --notes "$(cat <<'EOF'
# GhostMeter v0.1.0 — MVP Release

First public release of GhostMeter, a multi-protocol device simulator for energy management systems.

## Features

- **Modbus TCP** protocol simulation with pymodbus
- **Device Templates**: Built-in energy device register maps (3-phase meter, 1-phase meter, inverter)
- **Device Instances**: Create virtual devices from templates with unique slave IDs
- **Simulation Engine**: 5 data generation modes (static, random, daily curve, computed, accumulator)
- **Anomaly Injection**: Real-time and scheduled anomalies (spike, drift, flatline, out-of-range, data loss)
- **Fault Simulation**: Communication faults (delay, timeout, exception, intermittent)
- **Monitor Dashboard**: Real-time WebSocket visualization with charts and event log
- **Config Export/Import**: Full system snapshot for environment migration
- **Modern Web UI**: React + Ant Design management interface

## Quick Start

```bash
cp .env.example .env
docker compose up -d
# Open http://localhost:3000
# Modbus TCP: localhost:502
```

See [README.md](README.md) for full documentation.
EOF
)"
```
