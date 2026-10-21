from __future__ import annotations

import math

from ...geometry.footprints import corridor_metrics
from ...math_utils import cubic_smoothstep, kmh_to_mps
from ..straight_road import StraightRoadScenario


class OvertakeScenario(StraightRoadScenario):
    """Both branches overtake; CF waits for safe separation AHEAD of ego."""

    def initialize(self, config, layout, branch):
        super().initialize(config, layout, branch)
        self.merge_start = None

    def step(self, states, step_index):
        ego, actor = states["ego"], states["primary_risk_actor"]
        ego_s, actor_s = self.road.station(ego.location), self.road.station(actor.location)
        cfg, events = self.config["behavior"], []
        metrics = corridor_metrics(ego, actor, self.road.forward(ego_s))
        if self.state == "approaching" and self.decision_due(step_index, actor_s-ego_s >= cfg["decision_lead_m"]):
            self.decision_index = step_index
            self.state = "waiting_safe_gap"
            events.append(self.event("intervention", step_index))
        if self.state == "waiting_safe_gap":
            required = cfg["cf_safe_headway_seconds"]*max(ego.speed_mps, kmh_to_mps(self.config["ego_vehicle"]["target_speed_kmh"]))
            if self.branch == "R" or (metrics["actor_ahead"] and metrics["bumper_gap_m"] >= required):
                if actor_s+cfg["merge_length_m"] >= self.layout["maneuver_zone_end_m"]:
                    raise RuntimeError("Overtaking reentry would leave the protected zone")
                self.state, self.merge_start = "merging", actor_s
                events.append(self.event("merge_started", step_index, station_m=actor_s))
        lateral = self.layout["actor_lateral_m"]
        if self.merge_start is not None:
            lateral *= 1-cubic_smoothstep((actor_s+3-self.merge_start)/cfg["merge_length_m"])
            if self.state in {"merging", "settling"} and actor_s >= self.merge_start+cfg["merge_length_m"]:
                self.state = "settling"
                fx, fy = self.road.forward(actor_s)
                heading_error = abs((actor.rotation.z-math.degrees(math.atan2(fy, fx))+180)%360-180)
                offset = self.road.lateral(actor.location)
                lateral_velocity = -fy*actor.velocity.x+fx*actor.velocity.y
                # Passing the center once is not stabilization: do not announce
                # completion while still drifting outward into an overshoot.
                if abs(offset) <= cfg["completion_lateral_tolerance_m"] and heading_error <= cfg["completion_heading_tolerance_degrees"] and offset*lateral_velocity <= 0:
                    self.mark_completed(step_index, events, "merge_completed")
        speed = cfg["merge_speed_kmh"] if self.merge_start is not None else self.config["risk_actor"]["initial_speed_kmh"]
        return self.finish_step(states, step_index, kmh_to_mps(speed), lateral, events)
