"""Integration tests for simulation config and fault control API routes."""

import uuid

from httpx import AsyncClient

TEMPLATE_PAYLOAD = {
    "name": "Sim Test Meter",
    "protocol": "modbus_tcp",
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
        {
            "name": "current",
            "address": 2,
            "function_code": 4,
            "data_type": "float32",
            "byte_order": "big_endian",
            "scale_factor": 1.0,
            "unit": "A",
            "description": "Current",
            "sort_order": 1,
        },
    ],
}


async def _create_template_and_device(client: AsyncClient) -> tuple[str, str]:
    """Helper: create a template + device and return (template_id, device_id)."""
    resp = await client.post("/api/v1/templates", json=TEMPLATE_PAYLOAD)
    assert resp.status_code == 201
    template_id = resp.json()["data"]["id"]

    resp = await client.post(
        "/api/v1/devices",
        json={"template_id": template_id, "name": "Sim Device", "slave_id": 10},
    )
    assert resp.status_code == 201
    device_id = resp.json()["data"]["id"]
    return template_id, device_id


# --- Simulation Config Tests ---


class TestGetSimulationConfigs:
    async def test_empty_configs(self, client: AsyncClient) -> None:
        _, device_id = await _create_template_and_device(client)
        resp = await client.get(f"/api/v1/devices/{device_id}/simulation")
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    async def test_nonexistent_device_returns_404(self, client: AsyncClient) -> None:
        fake_id = str(uuid.uuid4())
        resp = await client.get(f"/api/v1/devices/{fake_id}/simulation")
        assert resp.status_code == 404


class TestSetSimulationConfigs:
    async def test_put_configs_success(self, client: AsyncClient) -> None:
        _, device_id = await _create_template_and_device(client)
        payload = {
            "configs": [
                {
                    "register_name": "voltage",
                    "data_mode": "static",
                    "mode_params": {"value": 220.0},
                },
                {
                    "register_name": "current",
                    "data_mode": "random",
                    "mode_params": {"min": 0, "max": 10},
                },
            ]
        }
        resp = await client.put(
            f"/api/v1/devices/{device_id}/simulation", json=payload
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 2
        names = {c["register_name"] for c in data}
        assert names == {"voltage", "current"}

    async def test_put_replaces_existing(self, client: AsyncClient) -> None:
        _, device_id = await _create_template_and_device(client)
        # Set initial config
        payload1 = {
            "configs": [
                {"register_name": "voltage", "data_mode": "static", "mode_params": {"value": 220}},
                {"register_name": "current", "data_mode": "static", "mode_params": {"value": 5}},
            ]
        }
        await client.put(f"/api/v1/devices/{device_id}/simulation", json=payload1)

        # Replace with only one config
        payload2 = {
            "configs": [
                {
                    "register_name": "voltage",
                    "data_mode": "random",
                    "mode_params": {"min": 200, "max": 240},
                },
            ]
        }
        resp = await client.put(
            f"/api/v1/devices/{device_id}/simulation", json=payload2
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["register_name"] == "voltage"
        assert data[0]["data_mode"] == "random"

    async def test_put_invalid_register_name(self, client: AsyncClient) -> None:
        _, device_id = await _create_template_and_device(client)
        payload = {
            "configs": [
                {"register_name": "nonexistent_reg", "data_mode": "static", "mode_params": {}},
            ]
        }
        resp = await client.put(
            f"/api/v1/devices/{device_id}/simulation", json=payload
        )
        assert resp.status_code == 422

    async def test_put_invalid_data_mode(self, client: AsyncClient) -> None:
        _, device_id = await _create_template_and_device(client)
        payload = {
            "configs": [
                {"register_name": "voltage", "data_mode": "invalid_mode", "mode_params": {}},
            ]
        }
        resp = await client.put(
            f"/api/v1/devices/{device_id}/simulation", json=payload
        )
        assert resp.status_code == 422

    async def test_put_duplicate_register_names(self, client: AsyncClient) -> None:
        _, device_id = await _create_template_and_device(client)
        payload = {
            "configs": [
                {
                    "register_name": "voltage",
                    "data_mode": "static",
                    "mode_params": {"value": 220},
                },
                {
                    "register_name": "voltage",
                    "data_mode": "random",
                    "mode_params": {"min": 200, "max": 240},
                },
            ]
        }
        resp = await client.put(
            f"/api/v1/devices/{device_id}/simulation", json=payload
        )
        assert resp.status_code == 422


class TestUpdateSimulationConfig:
    async def test_patch_creates_new_config(self, client: AsyncClient) -> None:
        _, device_id = await _create_template_and_device(client)
        payload = {
            "register_name": "voltage",
            "data_mode": "static",
            "mode_params": {"value": 230.0},
        }
        resp = await client.patch(
            f"/api/v1/devices/{device_id}/simulation/voltage", json=payload
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["register_name"] == "voltage"
        assert data["data_mode"] == "static"

    async def test_patch_updates_existing(self, client: AsyncClient) -> None:
        _, device_id = await _create_template_and_device(client)
        payload = {
            "register_name": "voltage",
            "data_mode": "static",
            "mode_params": {"value": 220},
        }
        await client.patch(
            f"/api/v1/devices/{device_id}/simulation/voltage", json=payload
        )

        # Update same register
        payload2 = {
            "register_name": "voltage",
            "data_mode": "random",
            "mode_params": {"min": 200, "max": 240},
        }
        resp = await client.patch(
            f"/api/v1/devices/{device_id}/simulation/voltage", json=payload2
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["data_mode"] == "random"

        # Verify only one config exists
        resp = await client.get(f"/api/v1/devices/{device_id}/simulation")
        assert len(resp.json()["data"]) == 1

    async def test_patch_invalid_register_name(self, client: AsyncClient) -> None:
        _, device_id = await _create_template_and_device(client)
        payload = {
            "register_name": "nonexistent",
            "data_mode": "static",
            "mode_params": {},
        }
        resp = await client.patch(
            f"/api/v1/devices/{device_id}/simulation/nonexistent", json=payload
        )
        assert resp.status_code == 422


class TestDeleteSimulationConfigs:
    async def test_delete_clears_all(self, client: AsyncClient) -> None:
        _, device_id = await _create_template_and_device(client)
        # Create configs first
        payload = {
            "configs": [
                {"register_name": "voltage", "data_mode": "static", "mode_params": {"value": 220}},
            ]
        }
        await client.put(f"/api/v1/devices/{device_id}/simulation", json=payload)

        # Delete all
        resp = await client.delete(f"/api/v1/devices/{device_id}/simulation")
        assert resp.status_code == 200

        # Verify empty
        resp = await client.get(f"/api/v1/devices/{device_id}/simulation")
        assert resp.json()["data"] == []

    async def test_delete_nonexistent_device_returns_404(self, client: AsyncClient) -> None:
        fake_id = str(uuid.uuid4())
        resp = await client.delete(f"/api/v1/devices/{fake_id}/simulation")
        assert resp.status_code == 404


# --- Fault Control Tests ---


class TestFaultControl:
    async def test_put_fault_success(self, client: AsyncClient) -> None:
        _, device_id = await _create_template_and_device(client)
        payload = {"fault_type": "delay", "params": {"delay_ms": 500}}
        resp = await client.put(
            f"/api/v1/devices/{device_id}/fault", json=payload
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["fault_type"] == "delay"
        assert data["params"] == {"delay_ms": 500}

    async def test_get_fault_after_set(self, client: AsyncClient) -> None:
        _, device_id = await _create_template_and_device(client)
        payload = {"fault_type": "timeout", "params": {}}
        await client.put(f"/api/v1/devices/{device_id}/fault", json=payload)

        resp = await client.get(f"/api/v1/devices/{device_id}/fault")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["fault_type"] == "timeout"

    async def test_get_fault_when_none_set(self, client: AsyncClient) -> None:
        _, device_id = await _create_template_and_device(client)
        resp = await client.get(f"/api/v1/devices/{device_id}/fault")
        assert resp.status_code == 200
        assert resp.json()["data"] is None

    async def test_delete_fault_clears(self, client: AsyncClient) -> None:
        _, device_id = await _create_template_and_device(client)
        # Set a fault
        await client.put(
            f"/api/v1/devices/{device_id}/fault",
            json={"fault_type": "exception", "params": {"exception_code": 4}},
        )

        # Clear it
        resp = await client.delete(f"/api/v1/devices/{device_id}/fault")
        assert resp.status_code == 200

        # Verify cleared
        resp = await client.get(f"/api/v1/devices/{device_id}/fault")
        assert resp.json()["data"] is None

    async def test_put_invalid_fault_type(self, client: AsyncClient) -> None:
        _, device_id = await _create_template_and_device(client)
        payload = {"fault_type": "invalid_type", "params": {}}
        resp = await client.put(
            f"/api/v1/devices/{device_id}/fault", json=payload
        )
        assert resp.status_code == 422

    async def test_put_exception_fault_on_mqtt_device_rejected(self, client: AsyncClient) -> None:
        """MQTT is publish-only — no request/response channel for an error, so
        the exception fault type is rejected with 422 and no state is left behind."""
        mqtt_template = {**TEMPLATE_PAYLOAD, "name": "MQTT Fault Template", "protocol": "mqtt"}
        resp = await client.post("/api/v1/templates", json=mqtt_template)
        assert resp.status_code == 201
        template_id = resp.json()["data"]["id"]

        resp = await client.post(
            "/api/v1/devices",
            json={"template_id": template_id, "name": "MQTT Fault Device", "slave_id": 11},
        )
        assert resp.status_code == 201
        device_id = resp.json()["data"]["id"]

        resp = await client.put(
            f"/api/v1/devices/{device_id}/fault",
            json={"fault_type": "exception", "params": {}},
        )
        assert resp.status_code == 422
        assert resp.json()["error_code"] == "VALIDATION_ERROR"

        # No orphan fault state was created
        resp = await client.get(f"/api/v1/devices/{device_id}/fault")
        assert resp.json()["data"] is None

        # The other fault types remain accepted for MQTT devices
        resp = await client.put(
            f"/api/v1/devices/{device_id}/fault",
            json={"fault_type": "timeout", "params": {}},
        )
        assert resp.status_code == 200


# --- Aggregate data mode (issue #95) ---


async def _create_meter(client: AsyncClient, template_id: str, name: str, slave_id: int) -> str:
    resp = await client.post(
        "/api/v1/devices",
        json={"template_id": template_id, "name": name, "slave_id": slave_id},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]["id"]


def _aggregate_body(register_name: str, sources: list[str], **extra) -> dict:
    return {
        "configs": [
            {
                "register_name": register_name,
                "data_mode": "aggregate",
                "mode_params": {"op": "sum", "sources": sources, **extra},
            },
        ],
    }


class TestAggregateConfigs:
    async def test_put_aggregate_by_name_and_id(self, client: AsyncClient) -> None:
        template_id, main_id = await _create_template_and_device(client)
        pm1 = await _create_meter(client, template_id, "PM-01", 11)
        pm2 = await _create_meter(client, template_id, "PM-02", 12)

        resp = await client.put(
            f"/api/v1/devices/{main_id}/simulation",
            json=_aggregate_body("current", ["PM-01", pm2]),
        )
        assert resp.status_code == 200, resp.text
        cfg = resp.json()["data"][0]
        assert cfg["data_mode"] == "aggregate"
        # Stored as given (names stay portable for export/import); defaults filled in
        assert cfg["mode_params"]["sources"] == ["PM-01", pm2]
        assert cfg["mode_params"]["on_missing"] == "last_known"
        assert pm1  # created, referenced by name above

    async def test_put_aggregate_unknown_source_422(self, client: AsyncClient) -> None:
        _, main_id = await _create_template_and_device(client)
        resp = await client.put(
            f"/api/v1/devices/{main_id}/simulation",
            json=_aggregate_body("current", ["PM-99"]),
        )
        assert resp.status_code == 422
        assert "PM-99" in resp.json()["detail"]

    async def test_put_aggregate_ambiguous_name_422(self, client: AsyncClient) -> None:
        template_id, main_id = await _create_template_and_device(client)
        await _create_meter(client, template_id, "PM", 11)
        await _create_meter(client, template_id, "PM", 12)
        resp = await client.put(
            f"/api/v1/devices/{main_id}/simulation",
            json=_aggregate_body("current", ["PM"]),
        )
        assert resp.status_code == 422
        assert "ambiguous" in resp.json()["detail"]

    async def test_put_aggregate_self_reference_422(self, client: AsyncClient) -> None:
        _, main_id = await _create_template_and_device(client)
        resp = await client.put(
            f"/api/v1/devices/{main_id}/simulation",
            json=_aggregate_body("current", ["Sim Device"]),
        )
        assert resp.status_code == 422
        assert "device itself" in resp.json()["detail"]

    async def test_put_aggregate_source_lacks_register_422(self, client: AsyncClient) -> None:
        template_id, main_id = await _create_template_and_device(client)
        await _create_meter(client, template_id, "PM-01", 11)
        resp = await client.put(
            f"/api/v1/devices/{main_id}/simulation",
            json=_aggregate_body("current", ["PM-01"], register="nonexistent"),
        )
        assert resp.status_code == 422
        assert "has no register 'nonexistent'" in resp.json()["detail"]

    async def test_put_aggregate_cross_template_by_register_name(
        self, client: AsyncClient,
    ) -> None:
        """Sources may live on a different template as long as the register exists."""
        _, main_id = await _create_template_and_device(client)
        other_template = {
            **TEMPLATE_PAYLOAD,
            "name": "Other Meter",
            "registers": [TEMPLATE_PAYLOAD["registers"][1]],  # only 'current'
        }
        resp = await client.post("/api/v1/templates", json=other_template)
        assert resp.status_code == 201
        other_id = resp.json()["data"]["id"]
        await _create_meter(client, other_id, "OTHER-01", 21)

        resp = await client.put(
            f"/api/v1/devices/{main_id}/simulation",
            json=_aggregate_body("current", ["OTHER-01"]),
        )
        assert resp.status_code == 200, resp.text
        resp = await client.put(
            f"/api/v1/devices/{main_id}/simulation",
            json=_aggregate_body("voltage", ["OTHER-01"]),
        )
        assert resp.status_code == 422
        assert "has no register 'voltage'" in resp.json()["detail"]

    async def test_put_aggregate_cycle_422(self, client: AsyncClient) -> None:
        template_id, main_id = await _create_template_and_device(client)
        pm1 = await _create_meter(client, template_id, "PM-01", 11)

        resp = await client.put(
            f"/api/v1/devices/{main_id}/simulation",
            json=_aggregate_body("current", ["PM-01"]),
        )
        assert resp.status_code == 200
        # PM-01 → Sim Device would close the loop
        resp = await client.put(
            f"/api/v1/devices/{pm1}/simulation",
            json=_aggregate_body("current", ["Sim Device"]),
        )
        assert resp.status_code == 422
        assert "cycle" in resp.json()["detail"]
        assert "PM-01" in resp.json()["detail"] and "Sim Device" in resp.json()["detail"]

    async def test_patch_aggregate_cycle_422(self, client: AsyncClient) -> None:
        template_id, main_id = await _create_template_and_device(client)
        pm1 = await _create_meter(client, template_id, "PM-01", 11)
        resp = await client.put(
            f"/api/v1/devices/{main_id}/simulation",
            json=_aggregate_body("current", ["PM-01"]),
        )
        assert resp.status_code == 200
        resp = await client.patch(
            f"/api/v1/devices/{pm1}/simulation/voltage",
            json={
                "register_name": "voltage",
                "data_mode": "aggregate",
                "mode_params": {"op": "sum", "sources": ["Sim Device"], "register": "current"},
            },
        )
        assert resp.status_code == 422
        assert "cycle" in resp.json()["detail"]

    async def test_patch_aggregate_replacing_own_register_is_not_a_cycle(
        self, client: AsyncClient,
    ) -> None:
        """Re-saving the same register with new sources must not see its old sources."""
        template_id, main_id = await _create_template_and_device(client)
        pm1 = await _create_meter(client, template_id, "PM-01", 11)
        pm2 = await _create_meter(client, template_id, "PM-02", 12)
        resp = await client.put(
            f"/api/v1/devices/{main_id}/simulation", json=_aggregate_body("current", ["PM-01"]),
        )
        assert resp.status_code == 200
        # PM-01 aggregates PM-02 (fine), then Sim Device switches current → PM-02 only
        resp = await client.put(
            f"/api/v1/devices/{pm1}/simulation", json=_aggregate_body("current", ["PM-02"]),
        )
        assert resp.status_code == 200
        resp = await client.patch(
            f"/api/v1/devices/{main_id}/simulation/current",
            json={
                "register_name": "current",
                "data_mode": "aggregate",
                "mode_params": {"op": "sum", "sources": ["PM-02"]},
            },
        )
        assert resp.status_code == 200, resp.text
        assert pm2

    async def test_schema_rejects_bad_params(self, client: AsyncClient) -> None:
        _, main_id = await _create_template_and_device(client)
        cases = [
            {"op": "median", "sources": ["PM-01"]},
            {"op": "sum", "sources": []},
            {"op": "sum", "sources": ["PM-01", "PM-01"]},
            {"op": "sum"},
            {"op": "weighted_avg", "sources": ["PM-01"]},
            {"op": "sum", "sources": ["PM-01"], "weight_register": "current"},
            {"op": "sum", "sources": ["PM-01"], "on_missing": "hold"},
        ]
        for params in cases:
            resp = await client.put(
                f"/api/v1/devices/{main_id}/simulation",
                json={"configs": [
                    {"register_name": "current", "data_mode": "aggregate", "mode_params": params},
                ]},
            )
            assert resp.status_code == 422, params

    async def test_weighted_avg_requires_weight_register_on_sources(
        self, client: AsyncClient,
    ) -> None:
        template_id, main_id = await _create_template_and_device(client)
        await _create_meter(client, template_id, "PM-01", 11)
        resp = await client.put(
            f"/api/v1/devices/{main_id}/simulation",
            json={"configs": [{
                "register_name": "current",
                "data_mode": "aggregate",
                "mode_params": {
                    "op": "weighted_avg", "sources": ["PM-01"], "weight_register": "voltage",
                },
            }]},
        )
        assert resp.status_code == 200, resp.text
        resp = await client.put(
            f"/api/v1/devices/{main_id}/simulation",
            json={"configs": [{
                "register_name": "current",
                "data_mode": "aggregate",
                "mode_params": {
                    "op": "weighted_avg", "sources": ["PM-01"], "weight_register": "power",
                },
            }]},
        )
        assert resp.status_code == 422
        assert "has no register 'power'" in resp.json()["detail"]
