from __future__ import annotations

import hashlib
import math

from ...actors import select_blueprint, actor_state
from ...carla_runtime import require_carla
from ...core.config import read_yaml
from ...core.models import ScenarioStep
from ...geometry.footprints import corridor_metrics
from ...geometry.routes import RoadRoute
from ...math_utils import cubic_smoothstep, kmh_to_mps
from ...models import Vec3
from ...runtime.session import transform_dict, ActorScope, spawn_exact
from ...control import SimpleVehicleController
from ...runtime.commands import apply_controls, initialize_motion


def _next(wp, spacing):
    choices = sorted(wp.next(spacing), key=lambda w: (w.road_id != wp.road_id, w.lane_id != wp.lane_id, w.road_id, w.lane_id))
    return choices[0] if choices else None


def find_sites(road_map, cfg):
    carla = require_carla()
    length = cfg["minimum_route_length_m"]
    spacing = cfg["route_spacing_m"]
    candidates = []
    for start in sorted(road_map.generate_waypoints(5.0), key=lambda w: (w.road_id, w.lane_id, w.s)):
        adjacent = start.get_left_lane()
        if start.is_junction or adjacent is None or adjacent.lane_type != carla.LaneType.Driving:
            continue
        f, a = start.transform.get_forward_vector(), adjacent.transform.get_forward_vector()
        if f.x*a.x+f.y*a.y < 0.99:
            continue
        behind = adjacent.previous(cfg["actor_start_behind_ego_m"])
        if not behind or behind[0].is_junction:
            continue
        if abs((behind[0].transform.rotation.yaw-start.transform.rotation.yaw+180)%360-180) > cfg["maximum_yaw_change_degrees"]:
            continue
        route, current, travel = [start], start, 0.0
        while travel < length:
            nxt = _next(current, spacing)
            if nxt is None:
                break
            other = nxt.get_left_lane()
            protected = travel <= cfg["maneuver_zone_length_m"]
            if protected and (nxt.is_junction or other is None or other.lane_type != carla.LaneType.Driving or other.is_junction):
                break
            yaw = abs((nxt.transform.rotation.yaw-start.transform.rotation.yaw+180)%360-180)
            nf = nxt.transform.get_forward_vector()
            af = other.transform.get_forward_vector() if other is not None else nf
            if yaw > cfg["maximum_yaw_change_degrees"] or (protected and af.x*nf.x+af.y*nf.y < 0.99):
                break
            travel += current.transform.location.distance(nxt.transform.location)
            route.append(nxt)
            current = nxt
        if travel >= length:
            candidates.append((start, behind[0], route))
    return candidates


class CutInScenario:
    def freeze_intervention(self, session, config, layout):
        """Freeze the common decision tick and preflight the longer CF route."""
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
            for role, key in (("ego","ego_spawn"),("primary_risk_actor","actor_spawn")):
                actors[role], transforms[role] = spawn_exact(world,layout["blueprints"][role],layout[key],role,scope)
            apply_controls(session.manager.client,actors,{role:carla.VehicleControl(brake=1.0) for role in actors})
            for _ in range(config["recording"]["warmup_frames"]):
                session.tick()
            initialize_motion(session.manager.client,actors,transforms,
                              {"ego":kmh_to_mps(config["ego_vehicle"]["initial_speed_kmh"]),
                               "primary_risk_actor":kmh_to_mps(config["risk_actor"]["initial_speed_kmh"])})
            reference = CutInScenario()
            reference.initialize(config,layout,"R")
            dt = config["carla"]["fixed_delta_seconds"]
            controllers = {role:SimpleVehicleController(actor,dt) for role,actor in actors.items()}
            road_map = world.get_map()
            decision_frozen = False
            for index in range(round(config["recording"]["max_episode_seconds"]/dt)):
                states = {role:actor_state(actor,road_map,role) for role,actor in actors.items()}
                result = reference.step(states,index)
                if not decision_frozen and any(e["event"]=="intervention" for e in result.events):
                    layout["intervention_step_index"] = index
                    layout["intervention_reference"] = {"source":"common_approach_rehearsal", "step_index":index,
                                                        "ego":states["ego"].as_dict(),"primary_risk_actor":states["primary_risk_actor"].as_dict()}
                    decision_frozen = True
                    reference = CutInScenario()
                    reference.initialize(config,layout,"CF")
                    result = reference.step(states,index)
                if decision_frozen and result.complete:
                    layout["intervention_reference"]["cf_site_preflight"] = {
                        "completed_step_index":index,"merge_station_m":reference.merge_start,
                        "tail_seconds":config["recording"]["post_maneuver_seconds"],
                        "ego_final_station_m":reference.road.station(states["ego"].location)}
                    return layout
                controls = {role:controllers[role].run_step(speed,target) for role,(speed,target) in result.targets.items()}
                apply_controls(session.manager.client,actors,controls)
                session.tick()
            raise RuntimeError("Site rehearsal did not reach the decision or complete CF plus recording tail")
        finally:
            scope.close()

    def plan(self, world, config):
        road_map = world.get_map()
        candidates = find_sites(road_map, config["placement"])
        if not candidates:
            raise RuntimeError("No sufficiently long non-junction adjacent lanes for R and yielding CF; inspect another site/map")
        site = config.get("site_selection", {"candidate_index": 0})
        index = int(site["candidate_index"])
        if not 0 <= index < len(candidates):
            raise ValueError(f"candidate_index {index} outside {len(candidates)} valid sites")
        ego_wp, actor_wp, waypoints = candidates[index]
        ego_spawn, actor_spawn = transform_dict(ego_wp.transform), transform_dict(actor_wp.transform)
        for spawn in (ego_spawn, actor_spawn):
            spawn["location"]["z"] += config["placement"]["spawn_z_offset_m"]
        route = [{"x": w.transform.location.x, "y": w.transform.location.y, "z": w.transform.location.z} for w in waypoints]
        road = RoadRoute(route)
        actor_lateral = road.lateral(Vec3(**actor_spawn["location"]))
        blueprints = world.get_blueprint_library()
        return {"schema_version": 2, "map": config["carla"]["map"],
                "map_fingerprint": hashlib.sha256(road_map.to_opendrive().encode()).hexdigest(),
                "candidate_index": index, "candidate_count": len(candidates),
                "road_id": ego_wp.road_id, "ego_lane_id": ego_wp.lane_id, "actor_lane_id": actor_wp.lane_id,
                "ego_spawn": ego_spawn, "actor_spawn": actor_spawn, "ego_route": route,
                "actor_lane_route": [road.at(s, actor_lateral).as_dict() for s in road.lengths],
                "actor_lateral_m": actor_lateral, "route_length_m": road.length,
                "maneuver_zone_end_m": config["placement"]["maneuver_zone_length_m"],
                "blueprints": {"ego": select_blueprint(blueprints, config["ego_vehicle"]["blueprint"]).id,
                               "primary_risk_actor": select_blueprint(blueprints, config["risk_actor"]["blueprint_candidates"]).id}}

    def initialize(self, config, layout, branch):
        self.config, self.layout, self.branch = config, layout, branch
        self.road = RoadRoute(layout["ego_route"])
        self.state = "approaching"
        self.merge_start = None
        self.completed_index = None
        self.merge_event = False

    def step(self, states, step_index):
        ego, actor = states["ego"], states["primary_risk_actor"]
        ego_s, actor_s = self.road.station(ego.location), self.road.station(actor.location)
        cfg = self.config["behavior"]
        metrics = corridor_metrics(ego, actor, self.road.forward(ego_s))
        events = []
        frozen_step = self.layout.get("intervention_step_index")
        decision = step_index >= frozen_step if frozen_step is not None else actor_s-ego_s >= cfg["decision_lead_m"]
        if self.state == "approaching" and decision:
            events.append({"event": "intervention", "step_index": step_index})
            if self.branch == "R":
                self.state, self.merge_start = "merging", actor_s
            else:
                self.state = "yielding"
        if self.state == "yielding":
            # Reserve clearance at the CF's planned merging speed, not its low yielding speed.
            required = cfg["cf_safe_headway_seconds"] * kmh_to_mps(cfg["cf_merge_speed_kmh"])
            if not metrics["actor_ahead"] and metrics["bumper_gap_m"] >= required:
                self.state, self.merge_start = "merging", actor_s
        if self.state == "merging" and not self.merge_event:
            if self.merge_start+cfg["merge_length_m"] >= self.layout["maneuver_zone_end_m"]:
                raise RuntimeError("Maneuver would leave the verified non-junction zone")
            self.merge_event = True
            events.append({"event": "merge_started", "step_index": step_index, "station_m": actor_s})
        actor_speed = kmh_to_mps(self.config["risk_actor"]["initial_speed_kmh"])
        if self.state == "yielding":
            actor_speed = kmh_to_mps(cfg["cf_yield_speed_kmh"])
        if self.branch == "CF" and self.state in {"merging", "completed"}:
            actor_speed = kmh_to_mps(cfg["cf_merge_speed_kmh"])
        lookahead = 3.0
        lateral = self.layout["actor_lateral_m"]
        if self.merge_start is not None:
            progress = (actor_s+lookahead-self.merge_start)/cfg["merge_length_m"]
            lateral *= 1.0-cubic_smoothstep(progress)
            if self.state == "merging" and actor_s >= self.merge_start+cfg["merge_length_m"] and abs(self.road.lateral(actor.location)) <= cfg["completion_lateral_tolerance_m"]:
                self.state, self.completed_index = "completed", step_index
                events.append({"event": "merge_completed", "step_index": step_index})
        if max(ego_s, actor_s)+lookahead >= self.road.length:
            raise RuntimeError("Frozen route exhausted before required recording tail; episode incomplete")
        complete = self.completed_index is not None and (step_index-self.completed_index)*self.config["carla"]["fixed_delta_seconds"] >= self.config["recording"]["post_maneuver_seconds"]
        return ScenarioStep({"ego": (kmh_to_mps(self.config["ego_vehicle"]["target_speed_kmh"]), self.road.at(ego_s+lookahead)),
                             "primary_risk_actor": (actor_speed, self.road.at(actor_s+lookahead, lateral))},
                            self.state, events, complete)
