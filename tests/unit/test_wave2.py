from copy import deepcopy
from dataclasses import replace

import pytest

from vn_traffic_risk.config import ConfigError
from vn_traffic_risk.core.batch import expand_batch
from vn_traffic_risk.core.config import PROJECT_ROOT, load_pair_config
from vn_traffic_risk.core.registry import get_scenario
from vn_traffic_risk.evaluation.risk import observe
from vn_traffic_risk.evaluation.scenario_checks import check_wave2
from vn_traffic_risk.geometry.footprints import lateral_clearance_metrics
from vn_traffic_risk.geometry.routes import RoadRoute
from vn_traffic_risk.models import ActorState, Vec3


def source(sid):
    return PROJECT_ROOT/f"configs/scenarios/{'group_b' if sid == 'INT-08' else 'group_a'}/{sid}.yaml"


def state(x=0, y=0, speed=7, extent=None, acceleration=0):
    return ActorState(1, "test", "vehicle.test", Vec3(x, y), Vec3(0, 0), Vec3(speed, 0),
                      Vec3(acceleration, 0), speed, 1, 1, extent or Vec3(1, 0.4, 1))


def setup(sid, branch):
    cfg = load_pair_config(source(sid)).data
    layout = {"ego_route": [{"x": 0, "y": 0, "z": 0}, {"x": 220, "y": 0, "z": 0}],
              "actor_lateral_m": 0 if sid == "INT-08" else -3.5, "maneuver_zone_end_m": 180,
              "intervention_step_index": 40}
    instance = get_scenario(sid)
    instance.initialize(cfg, layout, branch)
    return instance


@pytest.mark.parametrize("sid", ["INT-03", "INT-05", "INT-08"])
def test_new_configs_registry_modes_and_batch_are_coherent(sid):
    cfg = load_pair_config(source(sid))
    assert type(get_scenario(sid)) is type(get_scenario(sid))
    r, cf = cfg.branch("R"), cfg.branch("CF")
    assert r["ego_vehicle"] == cf["ego_vehicle"]
    assert r["placement"] == cf["placement"]
    batch, _, samples = expand_batch(PROJECT_ROOT/f"configs/batches/{sid.lower().replace('-', '_')}_pilot_managed.yaml")
    assert len(samples) == 3 and batch["baseline"] in samples
    with pytest.raises(ConfigError):
        load_pair_config(source(sid), {"interventions": {"R": {"ego_vehicle": {"target_speed_kmh": 50}}}})
    with pytest.raises(ConfigError):
        load_pair_config(source(sid), {"behavior": {"completion_lateral_tolerance_m": float("nan")}})


@pytest.mark.parametrize("sid", ["INT-03", "INT-05", "INT-08"])
def test_same_frozen_common_prefix_and_ego_target_without_branch_knowledge(sid):
    r, cf = setup(sid, "R"), setup(sid, "CF")
    states = {"ego": state(10, extent=Vec3(2.4, 0.95, 1)),
              "primary_risk_actor": state(13.5, 0 if sid == "INT-08" else -3.5)}
    assert r.step(states, 39) == cf.step(states, 39)
    risky, safe = r.step(states, 40), cf.step(states, 40)
    assert risky.targets["ego"] == safe.targets["ego"]
    assert [e for e in risky.events if e["event"] == "intervention"] == [e for e in safe.events if e["event"] == "intervention"]
    assert risky.targets["primary_risk_actor"] != safe.targets["primary_risk_actor"] or risky.state != safe.state


def test_squeeze_returns_to_original_lane_and_records_real_completion():
    r = setup("INT-03", "R")
    states = {"ego": state(14, extent=Vec3(2.4, 0.95, 1)), "primary_risk_actor": state(13, -3.5)}
    assert r.step(states, 40).state == "squeezing"
    assert abs(r.squeeze_lateral) == pytest.approx(1.65)
    states["primary_risk_actor"] = state(26, -1.65)
    assert r.step(states, 80).state == "holding_clearance"
    states["primary_risk_actor"] = state(33, -1.65)
    assert r.step(states, 100).state == "separating"
    states["primary_risk_actor"] = state(46, -3.5)
    result = r.step(states, 140)
    assert result.state == "completed" and not result.complete
    assert result.events[-1]["event"] == "maneuver_completed"
    assert r.step(states, 220).complete


def test_overtaking_cf_waits_for_gap_ahead_not_behind():
    cf = setup("INT-05", "CF")
    states = {"ego": state(10, extent=Vec3(2.4, 0.95, 1)), "primary_risk_actor": state(13.5, -3.5, 12.5)}
    assert cf.step(states, 40).state == "waiting_safe_gap"
    states.update(ego=state(60), primary_risk_actor=state(40, -3.5))
    assert cf.step(states, 80).state == "waiting_safe_gap"
    states.update(ego=state(40), primary_risk_actor=state(62, -3.5))
    result = cf.step(states, 100)
    assert result.state == "merging" and cf.merge_start == pytest.approx(62)
    assert result.targets["primary_risk_actor"][1].x > 62


def test_overtake_does_not_complete_on_the_first_centerline_crossing():
    r = setup("INT-05", "R")
    states = {"ego": state(10), "primary_risk_actor": state(13.5, -3.5)}
    r.step(states, 40)
    states["primary_risk_actor"] = replace(state(30, 0.2), rotation=Vec3(0, 0, 6))
    assert r.step(states, 60).state == "settling"
    states["primary_risk_actor"] = replace(state(31, 0.2), velocity=Vec3(7, 0.3))
    assert r.step(states, 61).state == "settling"
    states["primary_risk_actor"] = replace(state(32, 0.2), rotation=Vec3(0, 0, -1), velocity=Vec3(7, -0.1))
    result = r.step(states, 62)
    assert result.state == "completed" and result.events[-1]["event"] == "merge_completed"


@pytest.mark.parametrize("branch", ["R", "CF"])
def test_braking_reaches_target_then_recovers_and_completes(branch):
    scenario = setup("INT-08", branch)
    speed = 25/3.6
    events = []
    for index in range(39, 450):
        # Controlled kinematic fixture: validates the FSM, not CARLA physics.
        states = {"ego": state(10), "primary_risk_actor": state(34, speed=speed)}
        result = scenario.step(states, index)
        events.extend(result.events)
        speed = result.targets["primary_risk_actor"][0]
        if result.complete:
            break
    assert result.complete and speed == pytest.approx(25/3.6)
    by_name = {e["event"]: e["step_index"] for e in events}
    assert by_name["braking_started"] == (80 if branch == "R" else 40)
    assert by_name["braking_target_reached"] < by_name["maneuver_completed"]


def test_lateral_clearance_uses_bodies_and_requires_longitudinal_overlap():
    cfg = load_pair_config(source("INT-03")).data["risk_labelling"]
    ego = state(extent=Vec3(2.4, 0.95, 1))
    close = state(-1, -1.7)
    metrics = lateral_clearance_metrics(ego, close, (1, 0))
    assert metrics["lateral_clearance_m"] == pytest.approx(0.35)
    assert metrics["longitudinal_overlap"]
    assert "insufficient_lateral_clearance" in observe(ego, close, (1, 0), cfg)["reasons"]
    assert not observe(ego, replace(close, location=Vec3(30, -1.7)), (1, 0), cfg)["is_risk"]
    assert not observe(ego, state(-1, -3.5), (1, 0), cfg)["is_risk"]


def test_closing_ttc_detector_is_opt_in_and_uses_observations():
    cfg = load_pair_config(source("INT-08")).data["risk_labelling"]
    ego, lead = state(speed=10), state(22, speed=0)
    assert "critical_closing_ttc" in observe(ego, lead, (1, 0), cfg)["reasons"]
    legacy = load_pair_config(PROJECT_ROOT/"configs/scenarios/group_a/INT-01.yaml").data["risk_labelling"]
    assert "critical_closing_ttc" not in observe(ego, lead, (1, 0), legacy)["reasons"]


def test_cf_overtaking_acceptance_requires_ahead_not_legacy_behind():
    cfg = load_pair_config(source("INT-05")).data
    road = RoadRoute([{"x": 0, "y": 0, "z": 0}, {"x": 200, "y": 0, "z": 0}])
    frames = []
    for i in range(4):
        ego, actor = state(i), state(i-8, -3.5) if i == 0 else state(i+25)
        frames.append({"step_index": i, "ego": ego.as_dict(), "actors": [actor.as_dict()],
                       "risk": observe(ego, actor, (1, 0), cfg["risk_labelling"]),
                       "maneuver_state": "approaching" if i == 0 else "merging"})
    failures, _ = check_wave2(frames, {"intervention": {"step_index": 1}}, cfg, "CF", road)
    assert not failures
    wrong = deepcopy(frames)
    for row in wrong[1:]:
        actor = state(row["step_index"]-25)
        row["actors"] = [actor.as_dict()]
        row["risk"] = observe(state(row["step_index"]), actor, (1, 0), cfg["risk_labelling"])
    failures, _ = check_wave2(wrong, {"intervention": {"step_index": 1}}, cfg, "CF", road)
    assert "unsafe_cf_overtaking_reentry" in failures


@pytest.mark.parametrize("sid,override", [
    ("INT-03", {"risk_actor": {"initial_speed_kmh": 30}}),
    ("INT-03", {"behavior": {"risk_lateral_clearance_m": 0.7}}),
    ("INT-05", {"risk_actor": {"initial_speed_kmh": 20}}),
    ("INT-08", {"behavior": {"cf_deceleration_mps2": 5}}),
    ("INT-08", {"placement": {"actor_start_ahead_ego_m": -5}}),
    ("INT-08", {"behavior": {"risk_brake_delay_seconds": 0}}),
])
def test_invalid_physical_scenario_configs_rejected(sid, override):
    with pytest.raises(ConfigError):
        load_pair_config(source(sid), override)
