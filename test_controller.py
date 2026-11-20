
import pytest

from controller import EquipmentAPI


def test_verify_reading_success():
    reading = {
        "sensor_id": "pump-1",
        "sensor_status": "ready",
        "volume_reading": 10.0,
    }

    expected = {
        "sensor_id": "pump-1",
        "sensor_status": "ready",
        "volume_reading": 10.0,
    }

    result = EquipmentAPI.verify_reading(
        "pump-1",
        reading,
        expected,
    )

    assert result == reading


def test_verify_reading_failure():
    reading = {
        "sensor_id": "pump-1",
        "sensor_status": "ready",
        "volume_reading": 5.0,
    }

    expected = {
        "volume_reading": 10.0,
    }

    with pytest.raises(RuntimeError):
        EquipmentAPI.verify_reading(
            "pump-1",
            reading,
            expected,
        )


def test_verify_reading_missing_field():
    reading = {
        "sensor_id": "pump-1",
        "sensor_status": "ready",
    }

    expected = {
        "volume_reading": 10.0,
    }

    with pytest.raises(RuntimeError):
        EquipmentAPI.verify_reading(
            "pump-1",
            reading,
            expected,
        )
