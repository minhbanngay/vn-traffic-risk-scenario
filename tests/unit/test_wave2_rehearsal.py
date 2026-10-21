from types import SimpleNamespace

import pytest

from vn_traffic_risk.core.config import PROJECT_ROOT, load_pair_config
from vn_traffic_risk.core.models import ScenarioStep
from vn_traffic_risk.scenarios import straight_road as module


@pytest.mark.parametrize("failure", [None, "spawn", "cf"])
def test_generic_rehearsal_uses_concrete_scenario_and_always_cleans_up(monkeypatch, failure):
    calls = []
    config = load_pair_config(PROJECT_ROOT/"configs/scenarios/group_b/INT-08.yaml").data
    world = SimpleNamespace(get_settings=lambda: SimpleNamespace(), apply_settings=lambda value: None,
                            get_map=lambda: None)
    session = SimpleNamespace(world=world, reset=lambda: world, tick=lambda: None,
                              manager=SimpleNamespace(config={}, client=None))

    class Reference(module.StraightRoadScenario):
        def initialize(self, config, layout, branch):
            self.branch = branch
            self.road = SimpleNamespace(station=lambda point: point)
            calls.append(branch)

        def step(self, states, index):
            if self.branch == "CF" and failure == "cf":
                raise RuntimeError("CF preflight route exhausted")
            events = [{"event": "intervention"}] if index == 2 else []
            return ScenarioStep({"ego": (7, None), "primary_risk_actor": (5, None)}, "braking",
                                events, index >= 4, {"primary_risk_actor": 0.12})

    class Scope:
        def close(self):
            calls.append("cleanup")

    def spawn(world, blueprint, transform, role, scope):
        if failure == "spawn" and role == "primary_risk_actor":
            raise RuntimeError("Second spawn failed")
        return None, None

    limits = []
    monkeypatch.setattr(module, "ActorScope", Scope)
    monkeypatch.setattr(module, "require_carla", lambda: SimpleNamespace(VehicleControl=lambda **kwargs: None))
    monkeypatch.setattr(module, "spawn_exact", spawn)
    monkeypatch.setattr(module, "apply_controls", lambda *args: None)
    monkeypatch.setattr(module, "initialize_motion", lambda *args: None)
    monkeypatch.setattr(module, "actor_state", lambda *args: SimpleNamespace(location=100, as_dict=lambda: {"fixture": True}))
    monkeypatch.setattr(module, "vehicle_controller", lambda *args: SimpleNamespace(
        run_step=lambda speed, target, max_brake: limits.append(max_brake)))
    layout = {"blueprints": {"ego": "ego", "primary_risk_actor": "moto"}, "ego_spawn": {}, "actor_spawn": {}}
    if failure:
        with pytest.raises(RuntimeError):
            Reference().freeze_intervention(session, config, layout)
    else:
        result = Reference().freeze_intervention(session, config, layout)
        assert result["intervention_step_index"] == 2
        assert result["intervention_reference"]["cf_site_preflight"]["completed_step_index"] == 4
        assert calls[:2] == ["R", "CF"]
        assert 0.12 in limits
    assert calls[-1] == "cleanup"
