"""Shared site planning and physical preflight for straight-road interactions.

INT-01 keeps its original planner/rehearsal for reproducibility. New scenarios
reuse its validated adjacent-lane search, but never its cut-in state machine.
"""
from __future__ import annotations

from ..actors import actor_state
from ..carla_runtime import require_carla
from ..behaviors.controllers import vehicle_controller
from ..core.models import ScenarioStep
from ..geometry.routes import RoadRoute
from ..math_utils import kmh_to_mps
from ..runtime.commands import apply_controls, initialize_motion
from ..runtime.session import ActorScope, spawn_exact
from .group_a.int_01_cut_in import CutInScenario


class StraightRoadScenario:
    def plan(self, world, config):
        layout = CutInScenario().plan(world, config)
        layout["scenario_id"] = config["scenario"]["scenario_id"]
        return layout

    def freeze_intervention(self, session, config, layout):
        """Rehearse the common approach, then the actual CF through its tail.

        No image collection occurs here. Resources are registered immediately,
        and the same commands, warm-up length and brake limits are used at run.
        """
        settings = session.world.get_settings()
        settings.synchronous_mode = True
        settings.fixed_delta_seconds = config["carla"]["fixed_delta_seconds"]
        session.world.apply_settings(settings)
        session.manager.config["synchronous_mode"] = True
        world = session.reset()
        scope = ActorScope()
        carla = require_carla()
        try:
            actors, transforms = {}, {}
            for role, key in (("ego", "ego_spawn"), ("primary_risk_actor", "actor_spawn")):
                actors[role], transforms[role] = spawn_exact(world, layout["blueprints"][role], layout[key], role, scope)
            apply_controls(session.manager.client, actors, {r: carla.VehicleControl(brake=1.0) for r in actors})
            for _ in range(config["recording"]["warmup_frames"]):
                session.tick()
            initialize_motion(session.manager.client, actors, transforms,
                              {"ego": kmh_to_mps(config["ego_vehicle"]["initial_speed_kmh"]),
                               "primary_risk_actor": kmh_to_mps(config["risk_actor"]["initial_speed_kmh"])})
            reference = type(self)()
            reference.initialize(config, layout, "R")
            dt = config["carla"]["fixed_delta_seconds"]
            controllers = {r: vehicle_controller(a, dt, config, r) for r, a in actors.items()}
            road_map = world.get_map()
            frozen = False
            for index in range(round(config["recording"]["max_episode_seconds"]/dt)):
                states = {r: actor_state(a, road_map, r) for r, a in actors.items()}
                result = reference.step(states, index)
                if not frozen and any(e["event"] == "intervention" for e in result.events):
                    layout["intervention_step_index"] = index
                    layout["intervention_reference"] = {
                        "source": "common_approach_rehearsal", "step_index": index,
                        **{r: state.as_dict() for r, state in states.items()}}
                    frozen = True
                    reference = type(self)()
                    reference.initialize(config, layout, "CF")
                    result = reference.step(states, index)
                if frozen and result.complete:
                    layout["intervention_reference"]["cf_site_preflight"] = {
                        "completed_step_index": index,
                        "tail_seconds": config["recording"]["post_maneuver_seconds"],
                        "ego_final_station_m": reference.road.station(states["ego"].location)}
                    return layout
                controls = {r: controllers[r].run_step(speed, target, max_brake=result.brake_limits.get(r, 1.0))
                            for r, (speed, target) in result.targets.items()}
                apply_controls(session.manager.client, actors, controls)
                session.tick()
            raise RuntimeError("Site rehearsal did not complete the common decision, CF and recording tail")
        finally:
            scope.close()

    def initialize(self, config, layout, branch):
        if branch not in {"R", "CF"}:
            raise ValueError(branch)
        self.config, self.layout, self.branch = config, layout, branch
        self.road = RoadRoute(layout["ego_route"])
        self.state = "approaching"
        self.decision_index = self.completed_index = None
        self.dt = config["carla"]["fixed_delta_seconds"]

    def decision_due(self, index, condition):
        frozen = self.layout.get("intervention_step_index")
        return index >= frozen if frozen is not None else condition

    def event(self, name, index, **fields):
        return {"event": name, "step_index": index, **fields}

    def finish_step(self, states, index, speed, lateral, events, brake_limit=1.0):
        ego_s = self.road.station(states["ego"].location)
        actor_s = self.road.station(states["primary_risk_actor"].location)
        if max(ego_s, actor_s)+3.0 >= self.road.length:
            raise RuntimeError("Frozen route exhausted before required recording tail")
        if self.state != "completed" and max(ego_s, actor_s) >= self.layout["maneuver_zone_end_m"]:
            raise RuntimeError("Interaction left the verified non-junction maneuver zone")
        complete = self.completed_index is not None and (index-self.completed_index)*self.dt >= self.config["recording"]["post_maneuver_seconds"]
        return ScenarioStep({"ego": (kmh_to_mps(self.config["ego_vehicle"]["target_speed_kmh"]), self.road.at(ego_s+3.0)),
                             "primary_risk_actor": (speed, self.road.at(actor_s+3.0, lateral))},
                            self.state, events, complete, {"primary_risk_actor": brake_limit})

    def mark_completed(self, index, events, name="maneuver_completed"):
        self.state, self.completed_index = "completed", index
        events.append(self.event(name, index))
