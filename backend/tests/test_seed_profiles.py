"""Tests for simulation profile seed loading."""

from httpx import AsyncClient

from app.seed.loader import seed_builtin_profiles, seed_builtin_templates


class TestSeedProfiles:
    async def test_seed_creates_profiles(self, client: AsyncClient) -> None:
        """Seeding creates profiles for built-in templates."""
        await seed_builtin_templates()
        await seed_builtin_profiles()

        resp = await client.get("/api/v1/templates")
        templates = resp.json()["data"]
        assert len(templates) >= 3

        for t in templates:
            if not t.get("is_builtin"):
                continue
            resp = await client.get(
                f"/api/v1/simulation-profiles?template_id={t['id']}"
            )
            profiles = resp.json()["data"]
            assert len(profiles) >= 1, f"No profile for template {t['name']}"
            defaults = [p for p in profiles if p["is_default"]]
            assert len(defaults) == 1, f"Expected 1 default for {t['name']}"
            assert defaults[0]["is_builtin"] is True

    async def test_seed_is_idempotent(self, client: AsyncClient) -> None:
        """Running seed twice doesn't create duplicates."""
        await seed_builtin_templates()
        await seed_builtin_profiles()
        await seed_builtin_profiles()

        resp = await client.get("/api/v1/templates")
        templates = resp.json()["data"]
        for t in templates:
            if not t.get("is_builtin"):
                continue
            resp = await client.get(
                f"/api/v1/simulation-profiles?template_id={t['id']}"
            )
            profiles = resp.json()["data"]
            names = [p["name"] for p in profiles]
            assert len(names) == len(set(names)), f"Duplicate profiles for {t['name']}"

    async def test_builtin_profile_configs_cannot_be_updated(
        self, client: AsyncClient,
    ) -> None:
        """Built-in profile configs are immutable."""
        await seed_builtin_templates()
        await seed_builtin_profiles()

        resp = await client.get("/api/v1/templates")
        template = next(t for t in resp.json()["data"] if t.get("is_builtin"))
        resp = await client.get(
            f"/api/v1/simulation-profiles?template_id={template['id']}"
        )
        profile = next(p for p in resp.json()["data"] if p["is_builtin"])

        resp = await client.put(
            f"/api/v1/simulation-profiles/{profile['id']}",
            json={"configs": [{
                "register_name": "voltage",
                "data_mode": "static",
                "mode_params": {"value": 0},
            }]},
        )
        assert resp.status_code == 403

        resp = await client.put(
            f"/api/v1/simulation-profiles/{profile['id']}",
            json={"name": "Renamed"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "Renamed"

    async def test_builtin_profile_cannot_be_deleted(
        self, client: AsyncClient,
    ) -> None:
        """Built-in profiles cannot be deleted."""
        await seed_builtin_templates()
        await seed_builtin_profiles()

        resp = await client.get("/api/v1/templates")
        template = next(t for t in resp.json()["data"] if t.get("is_builtin"))
        resp = await client.get(
            f"/api/v1/simulation-profiles?template_id={template['id']}"
        )
        profile = next(p for p in resp.json()["data"] if p["is_builtin"])

        resp = await client.delete(f"/api/v1/simulation-profiles/{profile['id']}")
        assert resp.status_code == 403
