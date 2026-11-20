
import pytest
from fastapi.testclient import TestClient

from main import app, readings, device_registry, device_inboxes

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_data():
    """Clear simulated equipment data before every test."""
    for category in readings:
        readings[category].clear()

    device_registry.clear()
    device_inboxes.clear()

    yield


def test_health_check():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["server"] == "online"


def test_create_pump():
    pump = {
        "sensor_id": "pump-1",
        "sensor_status": "ready",
        "sensor_type": "Pump",
        "sensor_pressure": 1.0,
        "volume_reading": 5.0,
        "target_volume": 10.0,
    }

    response = client.post("/api/pumps", json=pump)

    assert response.status_code == 200
    assert response.json()["sensor_id"] == "pump-1"


def test_get_pumps():
    pump = {
        "sensor_id": "pump-1",
        "sensor_status": "ready",
        "sensor_type": "Pump",
        "sensor_pressure": 1.0,
        "volume_reading": 5.0,
        "target_volume": 10.0,
    }

    client.post("/api/pumps", json=pump)

    response = client.get("/api/pumps")

    assert response.status_code == 200
    assert "pump-1" in response.json()


def test_duplicate_sensor_id():
    pump = {
        "sensor_id": "device-1",
        "sensor_status": "ready",
        "sensor_type": "Pump",
        "sensor_pressure": 1.0,
        "volume_reading": 5.0,
        "target_volume": 10.0,
    }

    probe = {
        "sensor_id": "device-1",
        "sensor_status": "ready",
        "sensor_type": "Probe",
        "ph_probe_reading": 7.0,
        "container_size": 1.0,
    }

    client.post("/api/pumps", json=pump)

    response = client.post("/api/probes", json=probe)

    assert response.status_code == 409


def test_device_registry():
    pump = {
        "sensor_id": "pump-1",
        "sensor_status": "ready",
        "sensor_type": "Pump",
        "sensor_pressure": 1.0,
        "volume_reading": 5.0,
        "target_volume": 10.0,
    }

    client.post("/api/pumps", json=pump)

    response = client.get("/api/devices")

    assert response.status_code == 200
    assert response.json()["total_devices"] == 1


def test_pressure_check():
    pump = {
        "sensor_id": "pump-1",
        "sensor_status": "ready",
        "sensor_type": "Pump",
        "sensor_pressure": 2.0,
        "volume_reading": 5.0,
        "target_volume": 10.0,
    }

    valve = {
        "sensor_id": "valve-1",
        "sensor_status": "ready",
        "sensor_type": "Valve",
        "position_state": "Closed",
        "sensor_pressure": 1.5,
    }

    client.post("/api/pumps", json=pump)
    client.post("/api/valves", json=valve)

    response = client.get(
        "/api/pressure-check/pump-1/valve-1"
    )

    assert response.status_code == 200
    assert response.json()["comparison"] == "completed"
    assert response.json()["pressure_difference"] == 0.5


def test_simulation_reset():
    pump = {
        "sensor_id": "pump-1",
        "sensor_status": "ready",
        "sensor_type": "Pump",
        "sensor_pressure": 1.0,
        "volume_reading": 5.0,
        "target_volume": 10.0,
    }

    client.post("/api/pumps", json=pump)

    response = client.delete("/api/simulation/reset")

    assert response.status_code == 200
    assert response.json()["status"] == "success"

    response = client.get("/api/pumps")

    assert response.json() == {}
