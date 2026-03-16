async def test_health_returns_200(client):
    """Health endpoint should return 200 with expected fields."""
    response = await client.get("/health")

    assert response.status_code == 200

    data = response.json()
    assert "status" in data
    assert "database" in data
    assert "version" in data
    assert data["version"] == "0.1.0"


async def test_health_status_values(client):
    """Health endpoint status should be 'ok' or 'error'."""
    response = await client.get("/health")
    data = response.json()

    assert data["status"] in ("ok", "error")
    assert data["database"] in ("connected", "disconnected")
