"""Run a simulated station -> probe -> pump cycle against the Sensor Equipment API.

The API currently stores telemetry and does not control physical equipment. This
script simulates sensor readings and device states through the API's POST routes.
"""

import argparse
import logging
import time
from typing import Any

import httpx


LOGGER = logging.getLogger("controller")


class EquipmentAPI:
    def __init__(self, base_url: str, timeout: float = 5.0) -> None:
        self.client = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout)

    def close(self) -> None:
        self.client.close()

    def get(self, path: str) -> Any:
        response = self.client.get(path)
        response.raise_for_status()
        return response.json()

    def post(self, path: str, payload: dict[str, Any]) -> Any:
        response = self.client.post(path, json=payload)
        response.raise_for_status()
        return response.json()

    def get_equipment(self, category: str, sensor_id: str) -> dict[str, Any]:
        readings = self.get(f"/api/{category}")
        if not isinstance(readings, dict):
            raise RuntimeError(f"GET /api/{category} did not return an object")

        reading = readings.get(sensor_id)
        if not isinstance(reading, dict):
            raise RuntimeError(
                f"{sensor_id!r} was not present in GET /api/{category}"
            )
        return reading

    def post_and_verify(
        self, category: str, sensor_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        self.post(f"/api/{category}", payload)
        reading = self.get_equipment(category, sensor_id)
        return self.verify_reading(sensor_id, reading, payload)

    @staticmethod
    def verify_reading(
        sensor_id: str, reading: dict[str, Any], expected: dict[str, Any]
    ) -> dict[str, Any]:
        for field, value in expected.items():
            if reading.get(field) != value:
                raise RuntimeError(
                    f"{sensor_id} did not confirm {field}={value!r}; "
                    f"API returned {reading.get(field)!r}"
                )
        return reading


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Simulate the station, pH probe, valve, pump, and actuator workflow "
            "using the API's telemetry endpoints."
        )
    )
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--station-id", default="station-1")
    parser.add_argument("--actuator-id", default="actuator-1")
    parser.add_argument("--probe-id", default="probe-1")
    parser.add_argument("--valve-id", default="valve-1")
    parser.add_argument("--pump-id", default="pump-1")
    parser.add_argument(
        "--weight", type=float, default=1.0, help="Simulated station weight"
    )
    parser.add_argument(
        "--ph", type=float, default=7.0, help="Simulated pH reading"
    )
    parser.add_argument("--ph-min", type=float, default=6.5)
    parser.add_argument("--ph-max", type=float, default=8.5)
    parser.add_argument("--target-volume", type=float, default=10.0)
    parser.add_argument("--pump-step", type=float, default=1.0)
    parser.add_argument(
        "--pump-interval",
        type=float,
        default=0.25,
        help="Seconds between simulated pump readings",
    )
    return parser


def run_cycle(api: EquipmentAPI, args: argparse.Namespace) -> None:
    actuator_extended = False
    valve_open = False

    station = {
        "sensor_id": args.station_id,
        "sensor_status": "ready",
        "sensor_type": "Station",
        "station_id": args.station_id,
        "sensor_temperature": 20.0,
        "outside_temperature": 20.0,
        "sensor_weight": args.weight,
        "tank_volume": 50.0,
        "tank_detector": "Normal",
    }
    station_reading = api.post_and_verify("stations", args.station_id, station)
    LOGGER.info(
        "Station %s reports weight %.2f",
        args.station_id,
        station_reading["sensor_weight"],
    )

    if station_reading["sensor_weight"] <= 0:
        LOGGER.info("No material detected; cycle stopped without actuating equipment.")
        return

    actuator = {
        "sensor_id": args.actuator_id,
        "sensor_status": "busy",
        "sensor_type": "Actuator",
        "position_state": "Extended",
        "position_percentage": 100.0,
    }
    valve = {
        "sensor_id": args.valve_id,
        "sensor_status": "ready",
        "sensor_type": "Valve",
        "position_state": "Closed",
        "sensor_pressure": 1.0,
    }

    try:
        LOGGER.info("Lowering probe actuator.")
        api.post("/api/actuators", actuator)
        actuator_extended = True
        api.verify_reading(
            args.actuator_id,
            api.get_equipment("actuators", args.actuator_id),
            actuator,
        )

        probe = {
            "sensor_id": args.probe_id,
            "sensor_status": "ready",
            "sensor_type": "Probe",
            "ph_probe_reading": args.ph,
            "container_size": 1.0,
        }
        probe_reading = api.post_and_verify("probes", args.probe_id, probe)
        ph = probe_reading["ph_probe_reading"]
        LOGGER.info("Probe %s reports pH %.2f", args.probe_id, ph)
        if not args.ph_min <= ph <= args.ph_max:
            raise RuntimeError(
                f"pH {ph} is outside the accepted range "
                f"{args.ph_min}..{args.ph_max}; pumping was not started"
            )

        pump_reading = {
            "sensor_id": args.pump_id,
            "sensor_status": "ready",
            "sensor_type": "Pump",
            "sensor_pressure": 1.0,
            "volume_reading": 0.0,
            "target_volume": args.target_volume,
        }
        closed_valve = api.post_and_verify("valves", args.valve_id, valve)
        api.post_and_verify("pumps", args.pump_id, pump_reading)

        pressure = api.get(
            f"/api/pressure-check/{args.pump_id}/{args.valve_id}"
        )
        if pressure.get("comparison") != "completed":
            raise RuntimeError("Pump/valve pressure comparison did not complete")

        LOGGER.info("pH accepted; opening valve and starting pump.")
        valve.update(
            sensor_status="busy",
            position_state="Open",
            sensor_pressure=closed_valve["sensor_pressure"],
        )
        api.post("/api/valves", valve)
        valve_open = True
        api.verify_reading(
            args.valve_id,
            api.get_equipment("valves", args.valve_id),
            valve,
        )

        volume = 0.0
        pump_reading["sensor_status"] = "busy"
        while volume < args.target_volume:
            if args.pump_interval:
                time.sleep(args.pump_interval)
            volume = min(args.target_volume, volume + args.pump_step)
            pump_reading["volume_reading"] = volume
            api.post("/api/pumps", pump_reading)
            confirmed_pump = api.get_equipment("pumps", args.pump_id)
            if confirmed_pump.get("volume_reading") != volume:
                raise RuntimeError(
                    f"Pump volume {volume} was not confirmed by the API"
                )
            LOGGER.info("Pumped volume: %.2f / %.2f", volume, args.target_volume)

        pump_reading["sensor_status"] = "ready"
        api.post_and_verify("pumps", args.pump_id, pump_reading)

        valve.update(sensor_status="ready", position_state="Closed")
        api.post("/api/valves", valve)
        valve_open = False
        api.verify_reading(
            args.valve_id,
            api.get_equipment("valves", args.valve_id),
            valve,
        )

        actuator.update(
            sensor_status="ready",
            position_state="Retracted",
            position_percentage=0.0,
        )
        api.post("/api/actuators", actuator)
        actuator_extended = False
        api.verify_reading(
            args.actuator_id,
            api.get_equipment("actuators", args.actuator_id),
            actuator,
        )

        api.get("/api/devices")
        overview = api.get("/api/overview")
        LOGGER.info(
            "Cycle complete. Registered devices: %s",
            overview["total_devices"],
        )
    finally:
        if valve_open:
            valve.update(sensor_status="ready", position_state="Closed")
            api.post("/api/valves", valve)
        if actuator_extended:
            actuator.update(
                sensor_status="ready",
                position_state="Retracted",
                position_percentage=0.0,
            )
            api.post("/api/actuators", actuator)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = build_parser()
    args = parser.parse_args()

    if args.weight < 0:
        parser.error("--weight must be 0 or greater")
    if not 0 <= args.ph <= 14:
        parser.error("--ph must be between 0 and 14")
    if not 0 <= args.ph_min <= args.ph_max <= 14:
        parser.error("--ph-min and --ph-max must satisfy 0 <= min <= max <= 14")
    if args.target_volume <= 0:
        parser.error("--target-volume must be greater than 0")
    if args.pump_step <= 0:
        parser.error("--pump-step must be greater than 0")
    if args.pump_interval < 0:
        parser.error("--pump-interval must be 0 or greater")

    api = EquipmentAPI(args.api_url)
    try:
        run_cycle(api, args)
        return 0
    except (httpx.HTTPError, RuntimeError) as error:
        LOGGER.error("Cycle failed: %s", error)
        return 1
    finally:
        api.close()


if __name__ == "__main__":
    raise SystemExit(main())
