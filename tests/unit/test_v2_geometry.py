from dataclasses import replace

import pytest

from vn_traffic_risk.evaluation.risk import future_vectors, observe
from vn_traffic_risk.geometry.footprints import corridor_metrics
from vn_traffic_risk.geometry.routes import RoadRoute
from vn_traffic_risk.models import ActorState, Vec3


def state(x=0, y=0, vx=7, vy=0, yaw=0):
    return ActorState(1, "test", "vehicle.test", Vec3(x,y), Vec3(0,0,yaw), Vec3(vx,vy), Vec3(0,0),
                      (vx*vx+vy*vy)**0.5, 1, 1, Vec3(2,1,1))


def test_parallel_neighbor_not_risk_but_short_headway_is():
    cfg = {"unsafe_headway_seconds": 1.5, "prediction_seconds": 1.5}
    assert not observe(state(), state(1,3.5), (1,0), cfg)["is_risk"]
    metrics = observe(state(), state(8,0), (1,0), cfg)
    assert metrics["bumper_gap_m"] == pytest.approx(4)
    assert metrics["is_risk"] and metrics["time_headway_seconds"] == pytest.approx(4/7)


def test_prediction_detects_entering_actor_without_branch_input():
    cfg = {"unsafe_headway_seconds": 1.5, "prediction_seconds": 1.5}
    result = observe(state(), state(7,3.5,7,-2), (1,0), cfg)
    assert not result["corridor_overlap"]
    assert "predicted_corridor_conflict" in result["reasons"]


def test_rotated_footprint_changes_clearance():
    aligned = corridor_metrics(state(), state(9,0,yaw=0), (1,0))
    rotated = corridor_metrics(state(), state(9,0,yaw=90), (1,0))
    assert rotated["bumper_gap_m"] == pytest.approx(aligned["bumper_gap_m"]+1)


def test_bbox_local_offset_is_rotated_with_actor_heading():
    from vn_traffic_risk.geometry.footprints import footprint
    shifted = replace(state(yaw=90),bbox_offset=Vec3(2,0))
    vertices = footprint(shifted)
    assert sum(x for x,y in vertices)/4 == pytest.approx(0)
    assert sum(y for x,y in vertices)/4 == pytest.approx(2)


def test_future_vector_masks_unobserved_and_missing_steps():
    frames = [{"step_index": i, "risk": {"is_risk": i == 2}} for i in (0,1,2,4)]
    future_vectors(frames, 3, 0.1, 0.05)
    assert frames[0]["future_risk_vector"] == [1,0,0]
    assert frames[0]["future_risk_valid"] == [True,True,False]
    assert frames[-1]["future_risk_valid"] == [False]*3


def test_route_projection_and_extrapolation():
    route = RoadRoute([{"x": 0,"y": 0,"z":0},{"x":10,"y":0,"z":0},{"x":20,"y":0,"z":0}])
    assert route.station(Vec3(-3,3)) == pytest.approx(-3)
    assert route.at(7,-3) == Vec3(7,-3,0)
    assert route.lateral(Vec3(7,-3)) == pytest.approx(-3)
