"""Tests for simulation profile seed loading."""

from unittest.mock import patch

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.seed.loader import seed_builtin_profiles, seed_builtin_templates

settings = get_settings()


def _fresh_session_factory() -> async_sessionmaker[AsyncSession]:
    """Create a fresh session factory to avoid stale event loop connections."""
    engine = create_async_engine(settings.database_url_computed, echo=False)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class TestSeedProfiles:
    async def test_seed_creates_profiles(self, client: AsyncClient) -> None:
        """Seeding creates profiles for built-in templates."""
        factory = _fresh_session_factory()
        with patch("app.seed.loader.async_session_factory", factory):
            await seed_builtin_templates()
            await seed_builtin_profiles()

        # List templates to get IDs
        resp = await client.get("/api/v1/templates")
        templates = resp.json()["data"]
        assert len(templates) >= 3  # 3 built-in templates

        # Each built-in template should have at least one profile
        for t in templates:
            if not t.get("is_builtin"):
                continue
            resp = await client.get(
                f"/api/v1/simulation-profiles?template_id={t['id']}"
            )
            profiles = resp.json()["data"]
            assert len(profiles) >= 1, f"No profile for template {t['name']}"
            # Default profile should exist
            defaults = [p for p in profiles if p["is_default"]]
            assert len(defaults) == 1, f"Expected 1 default for {t['name']}"
            assert defaults[0]["is_builtin"] is True

    async def test_seed_is_idempotent(self, client: AsyncClient) -> None:
        """Running seed twice doesn't create duplicates."""
        factory = _fresh_session_factory()
        with patch("app.seed.loader.async_session_factory", factory):
            await seed_builtin_templates()
            await seed_builtin_profiles()
            await seed_builtin_profiles()  # Second run

        resp = await client.get("/api/v1/templates")
        templates = resp.json()["data"]
        for t in templates:
            if not t.get("is_builtin"):
                continue
            resp = await client.get(
                f"/api/v1/simulation-profiles?template_id={t['id']}"
            )
            profiles = resp.json()["data"]
            # Should still be exactly 1, not 2
            names = [p["name"] for p in profiles]
            assert len(names) == len(set(names)), f"Duplicate profiles for {t['name']}"

    async def test_builtin_profile_configs_cannot_be_updated(
        self, client: AsyncClient,
    ) -> None:
        """Built-in profile configs are immutable."""
        factory = _fresh_session_factory()
        with patch("app.seed.loader.async_session_factory", factory):
            await seed_builtin_templates()
            await seed_builtin_profiles()

        # Find a builtin profile
        resp = await client.get("/api/v1/templates")
        template = next(t for t in resp.json()["data"] if t.get("is_builtin"))
        resp = await client.get(
            f"/api/v1/simulation-profiles?template_id={template['id']}"
        )
        profile = next(p for p in resp.json()["data"] if p["is_builtin"])

        # Attempt to update configs -> 403
        resp = await client.put(
            f"/api/v1/simulation-profiles/{profile['id']}",
            json={"configs": [{"register_name": "voltage", "data_mode": "static", "mode_params": {"value": 0}}]},
        )
        assert resp.status_code == 403

        # But name/description update should work
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
        factory = _fresh_session_factory()
        with patch("app.seed.loader.async_session_factory", factory):
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
