
from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


# =====================================================
# APPLICATION
# =====================================================

app = FastAPI(
    title="Sensor Equipment API - Version 2",
    description="Centralized API and simulated device communication",
    version="2.0.0"
)


def current_time():
    return datetime.now(timezone.utc)


# =====================================================
# SENSOR STATUS
# =====================================================

class SensorStatus(str, Enum):
    READY = "ready"
    BUSY = "busy"
    FAULT = "fault"
    OFFLINE = "offline"
    STALE = "stale"


# =====================================================
# BASE SENSOR MODEL
# =====================================================

class SensorBase(BaseModel):
    sensor_id: str
    sensor_status: SensorStatus
    sensor_timestamp: datetime = Field(default_factory=current_time)


# =====================================================
# EQUIPMENT MODELS
# =====================================================

class Pump(SensorBase):
    sensor_type: Literal["Pump"] = "Pump"
    sensor_pressure: float
    volume_reading: float = Field(ge=0)
    target_volume: float = Field(ge=0)


class Probe(SensorBase):
    sensor_type: Literal["Probe"] = "Probe"
    ph_probe_reading: float
    probe_timestamp: datetime = Field(default_factory=current_time)
    container_size: float = Field(gt=0)


class Actuator(SensorBase):
    sensor_type: Literal["Actuator"] = "Actuator"
    position_state: Literal[
        "Extended", "Retracted", "Modulating"
    ]
    position_percentage: float = Field(ge=0, le=100)


class Valve(SensorBase):
    sensor_type: Literal["Valve"] = "Valve"
    position_state: Literal["Open", "Closed"]
    sensor_pressure: float


class Station(SensorBase):
    sensor_type: Literal["Station"] = "Station"
    station_id: str
    sensor_temperature: float
    outside_temperature: float
    sensor_weight: float = Field(ge=0)
    tank_volume: float = Field(ge=0, le=100)
    tank_detector: Literal["Normal", "Leak", "Burst", "Unknown"]



# =====================================================
# DEVICE MESSAGE MODEL
# =====================================================

class DeviceMessage(BaseModel):
    message_type: str
    payload: dict


# =====================================================
# IN-MEMORY STORAGE
# =====================================================

# Latest sensor reading for each device
readings = {
    "pumps": {},
    "probes": {},
    "actuators": {},
    "valves": {},
    "stations": {}
}

# Device ID -> equipment category
device_registry = {}

# Latest message received by each device
device_inboxes = {}


# =====================================================
# CENTRAL STORAGE FUNCTION
# =====================================================

def save_reading(category, data):

    sensor_id = data.sensor_id

    # Prevent one device ID from representing
    # two different equipment categories.

    existing_type = device_registry.get(sensor_id)

    if existing_type and existing_type != category:
        raise HTTPException(
            status_code=409,
            detail="Sensor ID already belongs to another device type"
        )

    # Save latest reading
    readings[category][sensor_id] = data.model_dump(mode="json")

    # Register device
    device_registry[sensor_id] = category

    return {
        "message": "Sensor reading received successfully",
        "sensor_id": sensor_id,
        "sensor_type": category,
        "data": readings[category][sensor_id]
    }


# =====================================================
# CENTRAL HEALTH CHECK
# =====================================================

@app.get("/health")
def health_check():

    return {
        "server": "online",
        "version": "2.0.0",
        "timestamp": current_time()
    }


# =====================================================
# PUMP ENDPOINTS
# =====================================================

@app.post("/api/pumps")
def receive_pump(data: Pump):
    return save_reading("pumps", data)


@app.get("/api/pumps")
def get_pumps():
    return readings["pumps"]


# =====================================================
# PROBE ENDPOINTS
# =====================================================

@app.post("/api/probes")
def receive_probe(data: Probe):
    return save_reading("probes", data)


@app.get("/api/probes")
def get_probes():
    return readings["probes"]


# =====================================================
# ACTUATOR ENDPOINTS
# =====================================================

@app.post("/api/actuators")
def receive_actuator(data: Actuator):
    return save_reading("actuators", data)


@app.get("/api/actuators")
def get_actuators():
    return readings["actuators"]


# =====================================================
# VALVE ENDPOINTS
# =====================================================

@app.post("/api/valves")
def receive_valve(data: Valve):
    return save_reading("valves", data)


@app.get("/api/valves")
def get_valves():
    return readings["valves"]


# =====================================================
# STATION ENDPOINTS
# =====================================================

@app.post("/api/stations")
def receive_station(data: Station):
    return save_reading("stations", data)


@app.get("/api/stations")
def get_stations():
    return readings["stations"]


# =====================================================
# CENTRAL DEVICE REGISTRY
# =====================================================

@app.get("/api/devices")
def get_all_devices():

    return {
        "registered_devices": device_registry,
        "total_devices": len(device_registry)
    }


@app.get("/api/devices/{sensor_id}")
def get_device(sensor_id: str):

    category = device_registry.get(sensor_id)

    if category is None:
        raise HTTPException(404, "Device not registered")

    return readings[category][sensor_id]


# =====================================================
# CENTRAL SYSTEM OVERVIEW
# =====================================================

@app.get("/api/overview")
def system_overview():

    overview = {}

    for category, devices in readings.items():

        overview[category] = {
            "total": len(devices),
            "devices": list(devices.values())
        }

    return {
        "server_status": "online",
        "total_devices": len(device_registry),
        "equipment": overview
    }


# =====================================================
# DIRECT DEVICE-TO-DEVICE MESSAGING
# =====================================================

@app.post("/api/devices/{source_id}/send/{target_id}")
def send_device_message(
    source_id: str,
    target_id: str,
    message: DeviceMessage
):

    # Verify sender unless it is the central server
    if source_id != "CENTRAL_SERVER":
        if source_id not in device_registry:
            raise HTTPException(404, "Source device not registered")

    # Verify recipient
    if target_id not in device_registry:
        raise HTTPException(404, "Target device not registered")

    # Create message
    message_data = {
        "source_id": source_id,
        "target_id": target_id,
        "message_type": message.message_type,
        "payload": message.payload,
        "timestamp": current_time().isoformat()
    }

    # Store latest received message
    device_inboxes[target_id] = message_data

    return {
        "message": "Device message delivered",
        "delivery_status": "success",
        "data": message_data
    }


# =====================================================
# DEVICE INBOX
# =====================================================

@app.get("/api/devices/{sensor_id}/inbox")
def get_device_inbox(sensor_id: str):

    if sensor_id not in device_registry:
        raise HTTPException(404, "Device not registered")

    return {
        "sensor_id": sensor_id,
        "latest_message": device_inboxes.get(sensor_id)
    }


# =====================================================
# PUMP AND VALVE PRESSURE COMPARISON
# =====================================================

@app.get("/api/pressure-check/{pump_id}/{valve_id}")
def pressure_check(pump_id: str, valve_id: str):

    pump = readings["pumps"].get(pump_id)
    valve = readings["valves"].get(valve_id)

    if pump is None:
        raise HTTPException(404, "Pump not found")

    if valve is None:
        raise HTTPException(404, "Valve not found")

    pump_pressure = pump["sensor_pressure"]
    valve_pressure = valve["sensor_pressure"]

    difference = abs(pump_pressure - valve_pressure)

    return {
        "pump_id": pump_id,
        "valve_id": valve_id,
        "pump_pressure": pump_pressure,
        "valve_pressure": valve_pressure,
        "pressure_difference": difference,
        "comparison": "completed",
        "note": "Comparison only. No equipment control performed."
    }


# =====================================================
# SIMULATION RESET
# =====================================================

@app.delete("/api/simulation/reset")
def reset_simulation():

    for category in readings:
        readings[category].clear()

    device_registry.clear()
    device_inboxes.clear()

    return {
        "message": "Simulation data cleared",
        "status": "success"
    }
