from __future__ import annotations

import math
from typing import Any, Iterable

from .carla_runtime import require_carla
from .models import ActorState, Vec3


def _vec3(value: Any) -> Vec3:
    return Vec3(float(value.x), float(value.y), float(value.z))


def select_blueprint(library: Any, candidates: str | Iterable[str]) -> Any:
    if isinstance(candidates, str):
        candidates = [candidates]
    candidate_list = list(candidates)
    for name in candidate_list:
        matches = library.filter(name)
        if matches:
            return matches[0]
    raise RuntimeError(f"No CARLA blueprint found for candidates: {candidate_list}")


def spawn_vehicle(
    world: Any,
    blueprint_candidates: str | Iterable[str],
    transform: Any,
    role_name: str,
) -> Any:
    blueprint = select_blueprint(world.get_blueprint_library(), blueprint_candidates)
    if blueprint.has_attribute("role_name"):
        blueprint.set_attribute("role_name", role_name)
    actor = world.try_spawn_actor(blueprint, transform)
    if actor is None:
        retry = type(transform)(transform.location, transform.rotation)
        retry.location.z += 0.5
        actor = world.try_spawn_actor(blueprint, retry)
    if actor is None:
        raise RuntimeError(f"Could not spawn '{role_name}' at {transform}")
    actor.set_autopilot(False)
    return actor


def set_forward_speed(actor: Any, transform: Any, speed_mps: float) -> None:
    """Start an actor at road speed using the resolved spawn heading."""
    carla = require_carla()
    # actor.get_transform() can briefly report the pre-physics default directly
    # after spawn. The resolved spawn transform is already authoritative here.
    forward = transform.rotation.get_forward_vector()
    actor.set_target_velocity(
        carla.Vector3D(
            x=float(forward.x) * speed_mps,
            y=float(forward.y) * speed_mps,
            z=float(forward.z) * speed_mps,
        )
    )


def actor_state(actor: Any, road_map: Any, role_name: str) -> ActorState:
    transform = actor.get_transform()
    velocity = actor.get_velocity()
    acceleration = actor.get_acceleration()
    speed_mps = math.sqrt(
        velocity.x * velocity.x + velocity.y * velocity.y + velocity.z * velocity.z
    )
    waypoint = road_map.get_waypoint(
        transform.location,
        project_to_road=True,
    )
    bbox = actor.bounding_box.extent
    return ActorState(
        actor_id=int(actor.id),
        role_name=role_name,
        type_id=str(actor.type_id),
        location=_vec3(transform.location),
        rotation=Vec3(
            float(transform.rotation.roll),
            float(transform.rotation.pitch),
            float(transform.rotation.yaw),
        ),
        velocity=_vec3(velocity),
        acceleration=_vec3(acceleration),
        speed_mps=speed_mps,
        road_id=int(waypoint.road_id) if waypoint else None,
        lane_id=int(waypoint.lane_id) if waypoint else None,
        bbox_extent=_vec3(bbox),
    )


def stop_and_destroy(actors: Iterable[Any]) -> None:
    for actor in reversed(list(actors)):
        if actor is None:
            continue
        try:
            if hasattr(actor, "stop"):
                actor.stop()
        except RuntimeError:
            pass
        try:
            if actor.is_alive:
                actor.destroy()
        except RuntimeError:
            pass
