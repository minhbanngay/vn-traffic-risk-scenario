from __future__ import annotations

from dataclasses import replace

from ..geometry.footprints import corridor_metrics, lateral_clearance_metrics
from ..models import ActorState, Vec3


def observe(ego: ActorState, actor: ActorState, forward: tuple[float, float], cfg: dict,
            collision_now: bool = False, collision_occurred: bool = False) -> dict:
    metrics = corridor_metrics(ego, actor, forward)
    reasons = []
    if metrics["corridor_overlap"] and metrics["time_headway_seconds"] < cfg["unsafe_headway_seconds"]:
        reasons.append("insufficient_corridor_headway")
    lateral_threshold = cfg.get("lateral_clearance_m")
    if lateral_threshold is not None:
        metrics.update(lateral_clearance_metrics(ego, actor, forward))
        if metrics["longitudinal_overlap"] and metrics["lateral_clearance_m"] < lateral_threshold:
            reasons.append("insufficient_lateral_clearance")
    closing_threshold = cfg.get("closing_ttc_seconds")
    if closing_threshold is not None and metrics["actor_ahead"] and metrics["ttc_seconds"] is not None and metrics["ttc_seconds"] < closing_threshold:
        reasons.append("critical_closing_ttc")
    predicted = False
    predicted_lateral = False
    # Prediction uses observations only, never branch or future annotations.
    for i in range(1, 16):
        t = float(cfg["prediction_seconds"]) * i / 15
        future = []
        for state in (ego, actor):
            future.append(replace(state, location=Vec3(state.location.x+state.velocity.x*t,
                                                      state.location.y+state.velocity.y*t, state.location.z)))
        fm = corridor_metrics(*future, forward)
        if fm["corridor_overlap"] and fm["time_headway_seconds"] < cfg["unsafe_headway_seconds"]:
            predicted = True
        if lateral_threshold is not None:
            lm = lateral_clearance_metrics(*future, forward)
            predicted_lateral |= lm["longitudinal_overlap"] and lm["lateral_clearance_m"] < lateral_threshold
        if predicted and (lateral_threshold is None or predicted_lateral):
            break
    if predicted:
        reasons.append("predicted_corridor_conflict")
    if predicted_lateral:
        reasons.append("predicted_lateral_conflict")
    if collision_now:
        reasons.append("collision_sensor")
    return {**metrics, "is_risk": bool(reasons), "reasons": reasons,
            "collision_now": collision_now, "collision_occurred": collision_occurred}


def future_vectors(frames: list[dict], horizon: int, horizon_step: float, dt: float) -> None:
    stride = round(horizon_step / dt)
    by_step = {row["step_index"]: row for row in frames}
    for row in frames:
        targets = [by_step.get(row["step_index"] + stride*h) for h in range(1, horizon+1)]
        row["future_risk_vector"] = [int(x["risk"]["is_risk"]) if x is not None else 0 for x in targets]
        row["future_risk_valid"] = [x is not None for x in targets]
