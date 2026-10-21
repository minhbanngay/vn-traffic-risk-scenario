from __future__ import annotations

import math

from ...geometry.footprints import footprint
from ...math_utils import cubic_smoothstep, kmh_to_mps
from ..straight_road import StraightRoadScenario


class LateralSqueezeScenario(StraightRoadScenario):
    """Parallel motorcycle narrows clearance (R), or keeps its lane (CF)."""

    def initialize(self, config, layout, branch):
        super().initialize(config, layout, branch)
        self.transition_start = self.hold_index = self.return_start = None
        self.squeeze_lateral = None

    def step(self, states, step_index):
        actor = states["primary_risk_actor"]
        actor_s = self.road.station(actor.location)
        cfg = self.config["behavior"]
        events = []
        if self.state == "approaching" and self.decision_due(step_index, step_index*self.dt >= cfg["decision_after_seconds"]):
            self.decision_index, self.transition_start = step_index, actor_s
            events += [self.event("intervention", step_index), self.event("maneuver_started", step_index)]
            self.state = "squeezing" if self.branch == "R" else "maintaining_clearance"
            # Use the actual frozen blueprints' body dimensions, not a bike-width constant.
            fx, fy = self.road.forward(actor_s)
            widths = []
            for state in (states["ego"], actor):
                projections = [-fy*x+fx*y for x, y in footprint(state)]
                widths.append((max(projections)-min(projections))/2)
            self.squeeze_lateral = math.copysign(sum(widths)+cfg["risk_lateral_clearance_m"], self.layout["actor_lateral_m"])
            if abs(self.squeeze_lateral) >= abs(self.layout["actor_lateral_m"]):
                raise RuntimeError("Site has insufficient initial lateral clearance")
        lateral = self.layout["actor_lateral_m"]
        length = cfg["transition_length_m"]
        if self.state == "squeezing":
            progress = cubic_smoothstep((actor_s+3-self.transition_start)/length)
            lateral += (self.squeeze_lateral-lateral)*progress
            if actor_s >= self.transition_start+length and abs(self.road.lateral(actor.location)-self.squeeze_lateral) <= cfg["completion_lateral_tolerance_m"]:
                self.state, self.hold_index = "holding_clearance", step_index
                events.append(self.event("squeeze_reached", step_index))
        if self.state == "holding_clearance":
            lateral = self.squeeze_lateral
            if (step_index-self.hold_index)*self.dt >= cfg["hold_seconds"]:
                self.state, self.return_start = "separating", actor_s
                events.append(self.event("separation_started", step_index))
        if self.state == "separating":
            progress = cubic_smoothstep((actor_s+3-self.return_start)/length)
            lateral = self.squeeze_lateral+(self.layout["actor_lateral_m"]-self.squeeze_lateral)*progress
            if actor_s >= self.return_start+length and abs(self.road.lateral(actor.location)-self.layout["actor_lateral_m"]) <= cfg["completion_lateral_tolerance_m"]:
                self.mark_completed(step_index, events)
        if self.state == "maintaining_clearance" and (step_index-self.decision_index)*self.dt >= cfg["cf_observation_seconds"]:
            self.mark_completed(step_index, events)
        return self.finish_step(states, step_index, kmh_to_mps(self.config["risk_actor"]["initial_speed_kmh"]), lateral, events)
