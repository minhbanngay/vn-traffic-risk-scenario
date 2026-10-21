from ..scenarios.group_a.int_01_cut_in import CutInScenario
from ..scenarios.group_a.int_03_lateral_squeeze import LateralSqueezeScenario
from ..scenarios.group_a.int_05_overtake import OvertakeScenario
from ..scenarios.group_b.int_08_lead_braking import LeadBrakingScenario


IMPLEMENTATIONS = {"INT-01": CutInScenario, "INT-03": LateralSqueezeScenario,
                   "INT-05": OvertakeScenario, "INT-08": LeadBrakingScenario}
INTERVENTION_MODES = {
    "INT-01": {"R": "cut_in_ahead", "CF": "yield_then_merge_behind"},
    "INT-03": {"R": "squeeze_laterally", "CF": "maintain_lateral_clearance"},
    "INT-05": {"R": "reenter_too_close", "CF": "overtake_then_reenter_safely"},
    "INT-08": {"R": "delayed_hard_brake", "CF": "early_gradual_brake"},
}
BATCH_FIELDS = {
    "INT-01": {"risk_actor.initial_speed_kmh", "placement.actor_start_behind_ego_m"},
    "INT-03": {"risk_actor.initial_speed_kmh", "placement.actor_start_behind_ego_m"},
    "INT-05": {"risk_actor.initial_speed_kmh", "placement.actor_start_behind_ego_m"},
    "INT-08": {"risk_actor.initial_speed_kmh", "placement.actor_start_ahead_ego_m"},
}
CALIBRATION_FIELDS = {"INT-01": "decision_lead_m", "INT-03": "decision_after_seconds",
                      "INT-05": "decision_lead_m", "INT-08": "decision_after_seconds"}


def get_scenario(scenario_id: str):
    if scenario_id not in IMPLEMENTATIONS:
        raise ValueError(f"Scenario {scenario_id} is planned, not implemented")
    return IMPLEMENTATIONS[scenario_id]()
