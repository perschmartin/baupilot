"""BauPilot — Health-Check-Tests."""


def test_root(client):
    """Root-Endpunkt gibt Service-Info zurueck."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "BauPilot API"
    assert data["version"] == "0.2.0"


def test_health(client):
    """Health-Endpunkt antwortet."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "baupilot-api"
    assert "status" in data
