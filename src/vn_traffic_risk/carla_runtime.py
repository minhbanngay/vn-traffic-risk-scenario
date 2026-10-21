from __future__ import annotations

import importlib
from dataclasses import dataclass
from types import ModuleType
from typing import Any


class CarlaUnavailableError(RuntimeError):
    pass


def require_carla() -> ModuleType:
    try:
        return importlib.import_module("carla")
    except ImportError as exc:
        raise CarlaUnavailableError(
            "CARLA Python API is not importable. Install the matching CARLA wheel "
            "or add CARLA/PythonAPI/carla to PYTHONPATH."
        ) from exc


@dataclass
class WorldManager:
    config: dict[str, Any]
    client: Any = None
    world: Any = None
    original_settings: Any = None

    def connect(self, client: Any = None) -> Any:
        carla = require_carla()
        self.client = client if client is not None else carla.Client(
            str(self.config["host"]), int(self.config["port"])
        )
        self.client.set_timeout(float(self.config["timeout_seconds"]))
        requested_map = str(self.config["map"])
        world = self.client.get_world()
        current_map = world.get_map().name.split("/")[-1]
        if current_map != requested_map:
            world = self.client.load_world(requested_map)
        self.world = world
        self.original_settings = world.get_settings()

        settings = world.get_settings()
        settings.synchronous_mode = bool(self.config["synchronous_mode"])
        settings.fixed_delta_seconds = float(self.config["fixed_delta_seconds"])
        settings.no_rendering_mode = bool(self.config.get("no_rendering_mode", False))
        world.apply_settings(settings)
        return world

    def apply_weather(self, weather_name: str) -> None:
        if self.world is None:
            raise RuntimeError("WorldManager.connect() must be called first")
        carla = require_carla()
        try:
            weather = getattr(carla.WeatherParameters, weather_name)
        except AttributeError as exc:
            raise ValueError(f"Unknown CARLA weather preset: {weather_name}") from exc
        self.world.set_weather(weather)

    def tick(self) -> Any:
        if self.world is None:
            raise RuntimeError("WorldManager.connect() must be called first")
        if bool(self.config["synchronous_mode"]):
            self.world.tick()
        else:
            self.world.wait_for_tick()
        return self.world.get_snapshot()

    def restore(self) -> None:
        if self.world is not None and self.original_settings is not None:
            self.world.apply_settings(self.original_settings)

