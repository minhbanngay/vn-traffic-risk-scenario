import pytest

from vn_traffic_risk.models import ActorState, Vec3
from vn_traffic_risk.risk import (
    build_future_risk_vectors,
    closest_approach,
    evaluate_risk,
    risk_intervals,
)


def state(actor_id: int, x: float, y: float, vx: float, vy: float) -> ActorState:
    return ActorState(
        actor_id=actor_id,
        role_name="ego" if actor_id == 1 else "risk_actor",
        type_id="vehicle.test",
        location=Vec3(x, y),
        rotation=Vec3(0, 0, 0),
        velocity=Vec3(vx, vy),
        acceleration=Vec3(0, 0, 0),
        speed_mps=(vx * vx + vy * vy) ** 0.5,
        road_id=1,
        lane_id=1,
        bbox_extent=Vec3(1, 1, 1),
    )


def test_closest_approach_for_crossing_paths() -> None:
    ego = state(1, -10, 0, 5, 0)
    actor = state(2, 0, -10, 0, 5)
    result = closest_approach(ego, actor, 5.0)
    assert result.time_seconds == pytest.approx(2.0)
    assert result.distance_m == pytest.approx(0.0)


def test_eta_conflict_creates_risk_label() -> None:
    thresholds = {
        "max_prediction_seconds": 5.0,
        "eta_difference_threshold_seconds": 1.0,
        "relevant_distance_to_merge_m": 45.0,
        "closest_approach_threshold_m": 2.5,
        "min_distance_threshold_m": 5.0,
    }
    result = evaluate_risk(
        ego=state(1, -10, 0, 5, 0),
        actor=state(2, 0, -10, 0, 5),
        ego_distance_to_merge_m=10.0,
        actor_distance_to_merge_m=10.0,
        maneuver_active=True,
        collision=False,
        interaction_type="interactive",
        thresholds=thresholds,
    )
    assert result.is_risk
    assert "merge_eta_conflict" in result.reasons


def test_future_risk_vector_uses_time_stride() -> None:
    mask = [False, False, True, True, True, False, False]
    vectors = build_future_risk_vectors(mask, horizon=3, horizon_step_seconds=0.1, fixed_delta_seconds=0.05)
    assert vectors[0] == [1, 1, 0]
    assert vectors[-1] == [0, 0, 0]


def test_multiple_intervals() -> None:
    assert risk_intervals(
        [10, 11, 12, 13, 14, 15],
        [False, True, True, False, True, False],
    ) == [
        {"risk_start": 11, "risk_end": 12},
        {"risk_start": 14, "risk_end": 14},
    ]

