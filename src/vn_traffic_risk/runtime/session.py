from __future__ import annotations

from typing import Any

from ..actors import stop_and_destroy
from ..carla_runtime import WorldManager, require_carla


class ActorScope:
    def __init__(self):
        self.actors: list[Any] = []

    def add(self, actor: Any) -> Any:
        self.actors.append(actor)
        return actor

    def close(self) -> None:
        stop_and_destroy(self.actors)
        self.actors.clear()


class PairSession:
    def __init__(self, config: dict):
        self.config = config
        self.manager = WorldManager(config["carla"])

    def __enter__(self):
        # Inspect before connect(), which may load a different map.
        carla = require_carla()
        client = carla.Client(self.config["carla"]["host"], self.config["carla"]["port"])
        client.set_timeout(self.config["carla"]["timeout_seconds"])
        # Owned engines are fresh for each worker. Do not redundantly load the
        # startup map here: connect selects the map, reset establishes physics.
        existing = client.get_world().get_actors()
        if existing.filter("vehicle.*") or existing.filter("walker.*"):
            raise RuntimeError("Paired collection requires an idle dedicated server; existing traffic was preserved")
        try:
            self.world = self.manager.connect(client=client)
            self.original_weather = self.world.get_weather()
            self.manager.apply_weather(self.config["environment"]["weather"])
            return self
        except BaseException:
            self.manager.restore()
            raise

    def reset(self):
        # CARLA determinism requires sync/fixed-delta before reload, retaining
        # those settings from the first frame of each repetition.
        self.world = self.manager.client.reload_world(False)
        self.manager.world = self.world
        settings = self.world.get_settings()
        if not settings.synchronous_mode or abs(settings.fixed_delta_seconds-self.config["carla"]["fixed_delta_seconds"]) > 1e-6:
            raise RuntimeError("Reload failed to preserve deterministic settings")
        self.manager.apply_weather(self.config["environment"]["weather"])
        return self.world

    def tick(self):
        return self.manager.tick()

    def __exit__(self, *args):
        try:
            self.world.set_weather(self.original_weather)
        finally:
            self.manager.restore()


def transform_dict(transform: Any) -> dict:
    p, r = transform.location, transform.rotation
    return {"location": {"x": p.x, "y": p.y, "z": p.z},
            "rotation": {"pitch": r.pitch, "yaw": r.yaw, "roll": r.roll}}


def spawn_exact(world: Any, blueprint_id: str, description: dict, role: str, scope: ActorScope):
    carla = require_carla()
    blueprint = world.get_blueprint_library().find(blueprint_id)
    blueprint.set_attribute("role_name", role)
    if blueprint.has_attribute("color"):
        choices = blueprint.get_attribute("color").recommended_values
        if choices:
            blueprint.set_attribute("color", choices[0])
    transform = carla.Transform(carla.Location(**description["location"]), carla.Rotation(**description["rotation"]))
    actor = world.try_spawn_actor(blueprint, transform)
    if actor is None:
        raise RuntimeError(f"Frozen spawn blocked for {role}; no per-branch spawn adjustment permitted")
    scope.add(actor)
    actor.set_autopilot(False)
    return actor, transform
