from types import SimpleNamespace

import pytest

from vn_traffic_risk.core.config import PROJECT_ROOT, load_pair_config
from vn_traffic_risk.core.models import ScenarioStep
from vn_traffic_risk.scenarios.group_a import int_01_cut_in as module


@pytest.mark.parametrize("route_failure", [False, True])
def test_rehearsal_checks_cf_tail_before_collecting_and_always_cleans_up(monkeypatch, route_failure):
    scenario = module.CutInScenario()
    config = load_pair_config(PROJECT_ROOT/"configs/scenarios/group_a/INT-01.yaml").data
    calls = []
    settings = SimpleNamespace(synchronous_mode=False, fixed_delta_seconds=None)
    world = SimpleNamespace(get_settings=lambda:settings, apply_settings=lambda value:None,
                            get_map=lambda:None)
    session = SimpleNamespace(world=world, reset=lambda:world, tick=lambda:None,
                              manager=SimpleNamespace(config={}, client=None))
    class Scope:
        def close(self): calls.append("cleanup")
    class Reference:
        merge_start = 45
        road = SimpleNamespace(station=lambda value: value)
        def initialize(self, config, layout, branch):
            self.branch = branch
            calls.append(branch)
        def step(self, states, index):
            if self.branch == "CF" and route_failure:
                raise RuntimeError("Route exhausted")
            events = [{"event":"intervention"}] if index == 2 else []
            return ScenarioStep({"ego":(7,None), "primary_risk_actor":(10,None)},
                                "completed" if index >= 4 else "approaching",events,index >= 4)
    monkeypatch.setattr(module,"CutInScenario",Reference)
    monkeypatch.setattr(module,"ActorScope",Scope)
    monkeypatch.setattr(module,"require_carla",lambda:SimpleNamespace(VehicleControl=lambda **kwargs:None))
    monkeypatch.setattr(module,"spawn_exact",lambda *args:(None,None))
    monkeypatch.setattr(module,"apply_controls",lambda *args:None)
    monkeypatch.setattr(module,"initialize_motion",lambda *args:None)
    monkeypatch.setattr(module,"actor_state",lambda *args:SimpleNamespace(location=100,as_dict=lambda:{"test":True}))
    monkeypatch.setattr(module,"SimpleVehicleController",lambda *args:SimpleNamespace(run_step=lambda *args:None))
    layout = {"blueprints":{"ego":"ego","primary_risk_actor":"moto"},"ego_spawn":{},"actor_spawn":{}}
    if route_failure:
        with pytest.raises(RuntimeError,match="Route exhausted"):
            scenario.freeze_intervention(session,config,layout)
    else:
        result = scenario.freeze_intervention(session,config,layout)
        assert result["intervention_step_index"] == 2
        assert result["intervention_reference"]["cf_site_preflight"]["completed_step_index"] == 4
    assert calls == ["R","CF","cleanup"]
