from __future__ import annotations

import copy

from ...math_utils import kmh_to_mps
from ...geometry.routes import RoadRoute
from ..straight_road import StraightRoadScenario


class LeadBrakingScenario(StraightRoadScenario):
    """CF brakes earlier/gently; R keeps pace then brakes abruptly.

    Target speed is integrated at a bounded acceleration/deceleration, and the
    physical controller's actual control and observed acceleration are recorded.
    Both return to their original cruise speed, avoiding an endless slow lead.
    """

    def plan(self, world, config):
        search = copy.deepcopy(config)
        search["placement"]["actor_start_behind_ego_m"] = config["placement"]["site_search_rear_clearance_m"]
        layout = super().plan(world, search)
        road = RoadRoute(layout["ego_route"])
        location = road.at(config["placement"]["actor_start_ahead_ego_m"]).as_dict()
        location["z"] += config["placement"]["spawn_z_offset_m"]
        layout["actor_spawn"] = {"location": location, "rotation": dict(layout["ego_spawn"]["rotation"])}
        layout["actor_lane_id"] = layout["ego_lane_id"]
        layout["actor_lateral_m"] = 0.0
        layout["actor_lane_route"] = list(layout["ego_route"])
        return layout

    def initialize(self, config, layout, branch):
        super().initialize(config, layout, branch)
        self.speed_target = kmh_to_mps(config["risk_actor"]["initial_speed_kmh"])
        self.hold_index = None

    def step(self, states, step_index):
        cfg, events = self.config["behavior"], []
        cruise = kmh_to_mps(self.config["risk_actor"]["initial_speed_kmh"])
        actor = states["primary_risk_actor"]
        if self.state == "approaching" and self.decision_due(step_index, step_index*self.dt >= cfg["decision_after_seconds"]):
            self.decision_index, self.state = step_index, "anticipating"
            events.append(self.event("intervention", step_index))
        delay = cfg["risk_brake_delay_seconds"] if self.branch == "R" else 0.0
        if self.state == "anticipating" and (step_index-self.decision_index)*self.dt >= delay:
            self.state = "braking"
            events += [self.event("maneuver_started", step_index), self.event("braking_started", step_index)]
        prefix = "risk" if self.branch == "R" else "cf"
        floor = kmh_to_mps(cfg[f"{prefix}_target_speed_kmh"])
        if self.state == "braking":
            self.speed_target = max(floor, self.speed_target-cfg[f"{prefix}_deceleration_mps2"]*self.dt)
            if self.speed_target <= floor+1e-6 and actor.speed_mps <= floor+cfg["speed_tolerance_mps"]:
                self.state, self.hold_index = "holding_speed", step_index
                events.append(self.event("braking_target_reached", step_index))
        if self.state == "holding_speed" and (step_index-self.hold_index)*self.dt >= cfg[f"{prefix}_hold_seconds"]:
            self.state = "recovering"
            events.append(self.event("recovery_started", step_index))
        if self.state == "recovering":
            self.speed_target = min(cruise, self.speed_target+cfg["recovery_acceleration_mps2"]*self.dt)
            if self.speed_target >= cruise-1e-6 and actor.speed_mps >= cruise-cfg["speed_tolerance_mps"]:
                self.mark_completed(step_index, events)
        brake_limit = cfg[f"{prefix}_max_brake"] if self.state != "approaching" else 1.0
        return self.finish_step(states, step_index, self.speed_target, 0.0, events, brake_limit)
