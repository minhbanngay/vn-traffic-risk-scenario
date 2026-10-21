from dataclasses import replace

from vn_traffic_risk.core.config import PROJECT_ROOT, load_pair_config
from vn_traffic_risk.models import ActorState, Vec3
from vn_traffic_risk.scenarios.group_a.int_01_cut_in import CutInScenario


def actor(x, y, speed):
    return ActorState(1,"test","vehicle.test",Vec3(x,y),Vec3(0,0),Vec3(speed,0),Vec3(0,0),speed,1,1,Vec3(1,0.5,1))


def scenario(branch):
    config = load_pair_config(PROJECT_ROOT/"configs/scenarios/group_a/INT-01.yaml").data
    instance = CutInScenario()
    instance.initialize(config, {"ego_route":[{"x":0,"y":0,"z":0},{"x":150,"y":0,"z":0}],
                                 "actor_lateral_m":-3.5,"maneuver_zone_end_m":100}, branch)
    return instance


def test_same_prefix_and_different_actor_decision():
    r, cf = scenario("R"), scenario("CF")
    common = {"ego":actor(10,0,7),"primary_risk_actor":actor(8,-3.5,10)}
    assert r.step(common,0) == cf.step(common,0)
    decision = {"ego":actor(10,0,7),"primary_risk_actor":actor(13,-3.5,10)}
    risky, safe = r.step(decision,1), cf.step(decision,1)
    assert risky.state == "merging" and safe.state == "yielding"
    assert risky.targets["ego"] == safe.targets["ego"]
    assert [e["event"] for e in safe.events] == ["intervention"]


def test_cf_uses_future_merge_speed_for_gap_and_does_not_return_to_old_point():
    cf = scenario("CF")
    cf.step({"ego":actor(10,0,7),"primary_risk_actor":actor(13,-3.5,10)},0)
    too_close = cf.step({"ego":actor(30,0,7),"primary_risk_actor":actor(24,-3.5,1)},1)
    assert too_close.state == "yielding"
    safe = cf.step({"ego":actor(60,0,7),"primary_risk_actor":actor(40,-3.5,3)},2)
    assert safe.state == "merging" and cf.merge_start == 40
    assert safe.targets["primary_risk_actor"][1].x > 40


def test_frozen_reference_tick_is_identical_in_both_branches():
    r, cf = scenario("R"), scenario("CF")
    for instance in (r,cf):
        instance.layout["intervention_step_index"] = 50
    states = {"ego":actor(10,0,7),"primary_risk_actor":actor(13,-3.5,10)}
    assert r.step(states,49).state == cf.step(states,49).state == "approaching"
    risky,safe = r.step(states,50),cf.step(states,50)
    assert risky.state == "merging" and safe.state == "yielding"
    assert risky.events[0]["step_index"] == safe.events[0]["step_index"] == 50
