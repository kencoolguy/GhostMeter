from httpx import AsyncClient

from app.seed.loader import seed_builtin_templates


class TestSeedLoader:
    async def test_seed_creates_builtin_templates(self, client: AsyncClient) -> None:
        await seed_builtin_templates()

        response = await client.get("/api/v1/templates")
        body = response.json()
        templates = body["data"]

        builtin = [t for t in templates if t["is_builtin"]]
        assert len(builtin) == 4

        names = {t["name"] for t in builtin}
        assert "SDM630 Three-Phase Meter" in names
        assert "SDM120 Single-Phase Meter" in names
        assert "SunSpec Solar Inverter" in names

    async def test_seed_is_idempotent(self, client: AsyncClient) -> None:
        await seed_builtin_templates()
        await seed_builtin_templates()

        response = await client.get("/api/v1/templates")
        templates = response.json()["data"]
        builtin = [t for t in templates if t["is_builtin"]]
        assert len(builtin) == 4

    async def test_builtin_template_cannot_be_deleted(
        self, client: AsyncClient,
    ) -> None:
        await seed_builtin_templates()

        response = await client.get("/api/v1/templates")
        builtin = [t for t in response.json()["data"] if t["is_builtin"]][0]

        response = await client.delete(f"/api/v1/templates/{builtin['id']}")
        assert response.status_code == 403
        assert response.json()["error_code"] == "BUILTIN_TEMPLATE_IMMUTABLE"

    async def test_builtin_template_cannot_be_updated(
        self, client: AsyncClient,
    ) -> None:
        await seed_builtin_templates()

        response = await client.get("/api/v1/templates")
        builtin = [t for t in response.json()["data"] if t["is_builtin"]][0]

        detail_response = await client.get(f"/api/v1/templates/{builtin['id']}")
        detail = detail_response.json()["data"]

        update_payload = {
            "name": "Hacked Name",
            "protocol": detail["protocol"],
            "registers": [
                {
                    "name": r["name"],
                    "address": r["address"],
                    "function_code": r["function_code"],
                    "data_type": r["data_type"],
                    "byte_order": r["byte_order"],
                    "scale_factor": r["scale_factor"],
                    "unit": r["unit"],
                    "description": r["description"],
                    "sort_order": r["sort_order"],
                }
                for r in detail["registers"]
            ],
        }
        response = await client.put(
            f"/api/v1/templates/{builtin['id']}", json=update_payload
        )
        assert response.status_code == 403
        assert response.json()["error_code"] == "BUILTIN_TEMPLATE_IMMUTABLE"

    async def test_builtin_template_can_be_cloned(
        self, client: AsyncClient,
    ) -> None:
        await seed_builtin_templates()

        response = await client.get("/api/v1/templates")
        builtin = [t for t in response.json()["data"] if t["is_builtin"]][0]

        response = await client.post(
            f"/api/v1/templates/{builtin['id']}/clone",
            json={"new_name": "My Custom Meter"},
        )
        assert response.status_code == 201
        clone = response.json()["data"]
        assert clone["name"] == "My Custom Meter"
        assert clone["is_builtin"] is False
