from copy import deepcopy
from types import SimpleNamespace

import pytest

from vn_traffic_risk.behaviors import controllers
from vn_traffic_risk.config import ConfigError
from vn_traffic_risk.core.config import PROJECT_ROOT, load_pair_config
from vn_traffic_risk.core.registry import get_scenario
from vn_traffic_risk.scenarios.group_a.int_01_cut_in import CutInScenario


@pytest.mark.parametrize("role", ["ego", "primary_risk_actor"])
def test_actor_gain_options_never_change_ego_controller(monkeypatch, role):
    calls = []
    monkeypatch.setattr(controllers, "SimpleVehicleController", lambda *args: calls.append(args))
    config = {"risk_actor": {"controller_gains": {"speed_kp": 0.2, "speed_ki": 0.0}}}
    controllers.vehicle_controller("fixture", 0.05, config, role)
    if role == "ego":
        assert calls == [("fixture", 0.05)]
    else:
        assert calls[0][2].speed_kp == 0.2 and calls[0][2].speed_ki == 0.0


@pytest.mark.parametrize("gains", [{"speed_kp": 0}, {"speed_ki": float("nan")}, {"ego_speed": 10}])
def test_invalid_gain_configuration_rejected(gains):
    with pytest.raises(ConfigError):
        load_pair_config(PROJECT_ROOT/"configs/scenarios/group_b/INT-08.yaml", {"risk_actor": {"controller_gains": gains}})


def test_lead_spawn_is_resolved_inside_its_own_scenario_without_mutating_config(monkeypatch):
    config = load_pair_config(PROJECT_ROOT/"configs/scenarios/group_b/INT-08.yaml").data
    before = deepcopy(config)
    def base_plan(self, world, search):
        assert search["placement"]["actor_start_behind_ego_m"] == 8
        return {"ego_route": [{"x": 0, "y": 0, "z": 0}, {"x": 130, "y": 0, "z": 0}],
                "ego_spawn": {"location": {"x": 0, "y": 0, "z": 0.25}, "rotation": {"yaw": 0, "pitch": 0, "roll": 0}},
                "ego_lane_id": 1, "actor_lane_id": 2, "actor_lateral_m": -3.5}
    monkeypatch.setattr(CutInScenario, "plan", base_plan)
    layout = get_scenario("INT-08").plan(None, config)
    assert layout["actor_spawn"]["location"] == {"x": 24, "y": 0, "z": 0.25}
    assert layout["actor_lane_id"] == layout["ego_lane_id"] and layout["actor_lateral_m"] == 0
    assert config == before
