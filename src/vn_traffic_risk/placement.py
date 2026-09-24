from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable

from .carla_runtime import require_carla
from .math_utils import cubic_hermite_curve, distance_2d
from .models import Vec3


@dataclass(frozen=True)
class ScenarioLayout:
    ego_spawn_transform: Any
    actor_spawn_transform: Any
    ego_route: list[Vec3]
    actor_route: list[Vec3]
    ego_merge_index: int
    actor_merge_start_index: int
    actor_merge_end_index: int
    conflict_point: Vec3
    description: dict[str, Any]


def _point(location: Any) -> Vec3:
    return Vec3(float(location.x), float(location.y), float(location.z))


def _same_direction(first: Any, second: Any) -> bool:
    a = first.transform.get_forward_vector()
    b = second.transform.get_forward_vector()
    return a.x * b.x + a.y * b.y > 0.85


def _select_branch(waypoints: Iterable[Any], reference: Any) -> Any | None:
    choices = list(waypoints)
    if not choices:
        return None
    same_lane = [
        wp for wp in choices
        if wp.road_id == reference.road_id and wp.lane_id == reference.lane_id
    ]
    return (same_lane or choices)[0]


def _walk(waypoint: Any, distance_m: float, forward: bool) -> Any | None:
    current = waypoint
    travelled = 0.0
    step = 1.0
    while travelled < distance_m:
        candidates = current.next(step) if forward else current.previous(step)
        next_wp = _select_branch(candidates, current)
        if next_wp is None:
            return None
        current = next_wp
        travelled += step
    return current


def _sample_forward(start: Any, distance_m: float, spacing_m: float) -> list[Any]:
    route = [start]
    travelled = 0.0
    current = start
    while travelled < distance_m:
        candidates = current.next(spacing_m)
        next_wp = _select_branch(candidates, current)
        if next_wp is None:
            break
        route.append(next_wp)
        travelled += current.transform.location.distance(next_wp.transform.location)
        current = next_wp
    return route


def _adjacent_candidates(waypoint: Any, side: str) -> list[Any]:
    candidates: list[Any] = []
    if side in ("left", "either"):
        left = waypoint.get_left_lane()
        if left is not None:
            candidates.append(left)
    if side in ("right", "either"):
        right = waypoint.get_right_lane()
        if right is not None:
            candidates.append(right)
    return candidates


def _yaw_change_degrees(before: Any, after: Any) -> float:
    delta = after.transform.rotation.yaw - before.transform.rotation.yaw
    return abs((delta + 180.0) % 360.0 - 180.0)


def _find_candidate_pairs(road_map: Any, config: dict[str, Any]) -> list[tuple[Any, Any]]:
    carla = require_carla()
    spacing = float(config["waypoint_spacing_m"])
    side = str(config["lane_change_side"]).lower()
    ego_before_distance = float(config["ego_distance_to_merge_m"])
    actor_before_distance = ego_before_distance + float(
        config["actor_start_behind_ego_m"]
    )
    after_distance = (
        float(config["merge_length_m"]) / 2.0
        + float(config["distance_after_merge_m"])
    )
    candidates: list[tuple[Any, Any]] = []
    ordered = sorted(
        road_map.generate_waypoints(spacing),
        key=lambda wp: (wp.road_id, wp.section_id, wp.lane_id, wp.s),
    )
    for waypoint in ordered:
        if waypoint.is_junction or waypoint.lane_type != carla.LaneType.Driving:
            continue
        before = _walk(waypoint, ego_before_distance, forward=False)
        after = _walk(waypoint, after_distance, forward=True)
        if (
            before is None
            or after is None
            or _yaw_change_degrees(before, after) > 8.0
        ):
            continue
        for adjacent in _adjacent_candidates(waypoint, side):
            if adjacent.lane_type != carla.LaneType.Driving:
                continue
            if not _same_direction(waypoint, adjacent):
                continue
            adjacent_before = _walk(adjacent, actor_before_distance, forward=False)
            adjacent_after = _walk(adjacent, after_distance, forward=True)
            if (
                adjacent_before is None
                or adjacent_after is None
                or _yaw_change_degrees(adjacent_before, adjacent_after) > 8.0
            ):
                continue
            candidates.append((waypoint, adjacent))
    return candidates


def list_automatic_cut_in_candidates(
    road_map: Any,
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for index, (ego_lane, actor_lane) in enumerate(_find_candidate_pairs(road_map, config)):
        location = ego_lane.transform.location
        result.append(
            {
                "candidate_index": index,
                "road_id": int(ego_lane.road_id),
                "section_id": int(ego_lane.section_id),
                "ego_lane_id": int(ego_lane.lane_id),
                "actor_lane_id": int(actor_lane.lane_id),
                "s": float(ego_lane.s),
                "location": {
                    "x": float(location.x),
                    "y": float(location.y),
                    "z": float(location.z),
                },
            }
        )
    return result


def _nearest_index(points: list[Vec3], target: Vec3) -> int:
    return min(range(len(points)), key=lambda index: distance_2d(points[index], target))


def build_automatic_cut_in_layout(road_map: Any, config: dict[str, Any]) -> ScenarioLayout:
    carla = require_carla()
    pairs = _find_candidate_pairs(road_map, config)
    if not pairs:
        raise RuntimeError(
            "Could not find a straight, non-junction, same-direction adjacent-lane pair. "
            "Try another map or reduce the placement distances."
        )
    candidate_index = int(config.get("candidate_index", 0))
    if candidate_index >= len(pairs):
        raise IndexError(
            f"placement.candidate_index={candidate_index}, but only {len(pairs)} "
            "candidate locations were found"
        )
    merge_lane_wp, adjacent_wp = pairs[candidate_index]
    ego_start = _walk(
        merge_lane_wp,
        float(config["ego_distance_to_merge_m"]),
        forward=False,
    )
    actor_start_distance = float(config["ego_distance_to_merge_m"]) + float(
        config["actor_start_behind_ego_m"]
    )
    actor_start = _walk(
        adjacent_wp,
        actor_start_distance,
        forward=False,
    )
    merge_half = float(config["merge_length_m"]) / 2.0
    actor_merge_start = _walk(adjacent_wp, merge_half, forward=False)
    ego_merge_end = _walk(merge_lane_wp, merge_half, forward=True)
    if any(item is None for item in (ego_start, actor_start, actor_merge_start, ego_merge_end)):
        raise RuntimeError("The selected lane pair is too short for the configured scenario")

    total_ego_distance = (
        float(config["ego_distance_to_merge_m"])
        + float(config["distance_after_merge_m"])
    )
    ego_waypoints = _sample_forward(
        ego_start,
        total_ego_distance,
        float(config["waypoint_spacing_m"]),
    )
    adjacent_distance = max(
        2.0,
        actor_start_distance - merge_half,
    )
    actor_pre_merge = _sample_forward(
        actor_start,
        adjacent_distance,
        float(config["waypoint_spacing_m"]),
    )
    start_point = _point(actor_merge_start.transform.location)
    end_point = _point(ego_merge_end.transform.location)
    merge_samples = max(6, round(float(config["merge_length_m"]) / 1.0))
    start_forward = actor_merge_start.transform.get_forward_vector()
    end_forward = ego_merge_end.transform.get_forward_vector()
    tangent_scale = max(
        float(config["merge_length_m"]) * 0.65,
        distance_2d(start_point, end_point),
    )
    merge_curve = cubic_hermite_curve(
        start_point,
        end_point,
        Vec3(float(start_forward.x), float(start_forward.y), 0.0),
        Vec3(float(end_forward.x), float(end_forward.y), 0.0),
        merge_samples,
        tangent_scale,
    )
    ego_post_merge = _sample_forward(
        ego_merge_end,
        float(config["distance_after_merge_m"]),
        float(config["waypoint_spacing_m"]),
    )

    ego_route = [_point(wp.transform.location) for wp in ego_waypoints]
    actor_route = [_point(wp.transform.location) for wp in actor_pre_merge]
    if distance_2d(actor_route[-1], start_point) > 0.25:
        actor_route.append(start_point)
    actor_merge_start_index = len(actor_route) - 1
    actor_route.extend(merge_curve[1:])
    actor_merge_end_index = len(actor_route) - 1
    actor_route.extend(_point(wp.transform.location) for wp in ego_post_merge[1:])
    conflict_point = end_point
    ego_merge_index = _nearest_index(ego_route, conflict_point)

    z_offset = float(config.get("spawn_z_offset_m", 0.25))
    ego_transform = carla.Transform(ego_start.transform.location, ego_start.transform.rotation)
    actor_transform = carla.Transform(actor_start.transform.location, actor_start.transform.rotation)
    ego_transform.location.z += z_offset
    actor_transform.location.z += z_offset

    return ScenarioLayout(
        ego_spawn_transform=ego_transform,
        actor_spawn_transform=actor_transform,
        ego_route=ego_route,
        actor_route=actor_route,
        ego_merge_index=ego_merge_index,
        actor_merge_start_index=actor_merge_start_index,
        actor_merge_end_index=actor_merge_end_index,
        conflict_point=conflict_point,
        description={
            "road_id": int(merge_lane_wp.road_id),
            "ego_lane_id": int(merge_lane_wp.lane_id),
            "actor_lane_id": int(adjacent_wp.lane_id),
            "merge_s": float(merge_lane_wp.s),
            "candidate_count": len(pairs),
            "candidate_index": candidate_index,
            "actor_start_behind_ego_m": float(
                config["actor_start_behind_ego_m"]
            ),
        },
    )
