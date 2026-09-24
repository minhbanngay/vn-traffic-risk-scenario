from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .math_utils import distance_2d
from .models import ActorState, RiskObservation


@dataclass(frozen=True)
class ClosestApproach:
    time_seconds: float | None
    distance_m: float | None


def safe_eta(distance_m: float, speed_mps: float) -> float | None:
    if distance_m < 0:
        return None
    if speed_mps < 0.1:
        return None
    return distance_m / speed_mps


def closest_approach(
    ego: ActorState,
    actor: ActorState,
    max_prediction_seconds: float,
) -> ClosestApproach:
    rx = actor.location.x - ego.location.x
    ry = actor.location.y - ego.location.y
    rvx = actor.velocity.x - ego.velocity.x
    rvy = actor.velocity.y - ego.velocity.y
    denominator = rvx * rvx + rvy * rvy
    if denominator < 1e-6:
        return ClosestApproach(None, math.hypot(rx, ry))
    time_seconds = -(rx * rvx + ry * rvy) / denominator
    if time_seconds < 0.0 or time_seconds > max_prediction_seconds:
        return ClosestApproach(None, None)
    closest_x = rx + rvx * time_seconds
    closest_y = ry + rvy * time_seconds
    return ClosestApproach(time_seconds, math.hypot(closest_x, closest_y))


def evaluate_risk(
    *,
    ego: ActorState,
    actor: ActorState,
    ego_distance_to_merge_m: float,
    actor_distance_to_merge_m: float,
    maneuver_active: bool,
    collision: bool,
    interaction_type: str,
    thresholds: dict[str, Any],
) -> RiskObservation:
    distance = distance_2d(ego.location, actor.location)
    eta_ego = safe_eta(ego_distance_to_merge_m, ego.speed_mps)
    eta_actor = safe_eta(actor_distance_to_merge_m, actor.speed_mps)
    eta_difference = None
    if eta_ego is not None and eta_actor is not None:
        eta_difference = eta_actor - eta_ego

    approach = closest_approach(
        ego,
        actor,
        float(thresholds["max_prediction_seconds"]),
    )
    reasons: list[str] = []
    if collision:
        reasons.append("collision_sensor")

    eta_conflict = (
        maneuver_active
        and eta_difference is not None
        and abs(eta_difference)
        <= float(thresholds["eta_difference_threshold_seconds"])
        and ego_distance_to_merge_m
        <= float(thresholds["relevant_distance_to_merge_m"])
        and actor_distance_to_merge_m
        <= float(thresholds["relevant_distance_to_merge_m"])
    )
    if eta_conflict:
        reasons.append("merge_eta_conflict")

    predicted_close = (
        maneuver_active
        and approach.distance_m is not None
        and approach.distance_m
        <= float(thresholds["closest_approach_threshold_m"])
    )
    if predicted_close:
        reasons.append("predicted_close_approach")

    currently_close = (
        maneuver_active
        and distance <= float(thresholds["min_distance_threshold_m"])
    )
    if currently_close:
        reasons.append("current_distance")

    is_risk = bool(collision or eta_conflict or predicted_close or currently_close)
    effective_type = "collision" if collision else interaction_type
    return RiskObservation(
        is_risk=is_risk,
        interaction_type=effective_type,
        risk_actor_id=actor.actor_id,
        distance_m=distance,
        eta_ego_seconds=eta_ego,
        eta_actor_seconds=eta_actor,
        eta_difference_seconds=eta_difference,
        closest_approach_time_seconds=approach.time_seconds,
        closest_approach_distance_m=approach.distance_m,
        collision=collision,
        reasons=tuple(reasons),
    )


def build_future_risk_vectors(
    risk_mask: list[bool],
    horizon: int,
    horizon_step_seconds: float,
    fixed_delta_seconds: float,
) -> list[list[int]]:
    if horizon <= 0:
        raise ValueError("horizon must be positive")
    if horizon_step_seconds <= 0 or fixed_delta_seconds <= 0:
        raise ValueError("time steps must be positive")
    frame_stride = max(1, round(horizon_step_seconds / fixed_delta_seconds))
    result: list[list[int]] = []
    for current in range(len(risk_mask)):
        vector: list[int] = []
        for step in range(1, horizon + 1):
            future = current + step * frame_stride
            vector.append(int(risk_mask[future]) if future < len(risk_mask) else 0)
        result.append(vector)
    return result


def risk_intervals(frame_ids: list[int], risk_mask: list[bool]) -> list[dict[str, int]]:
    if len(frame_ids) != len(risk_mask):
        raise ValueError("frame_ids and risk_mask must have equal length")
    intervals: list[dict[str, int]] = []
    start: int | None = None
    previous: int | None = None
    for frame_id, is_risk in zip(frame_ids, risk_mask):
        if is_risk and start is None:
            start = frame_id
        if not is_risk and start is not None:
            intervals.append({"risk_start": start, "risk_end": previous or start})
            start = None
        previous = frame_id
    if start is not None:
        intervals.append({"risk_start": start, "risk_end": previous or start})
    return intervals

