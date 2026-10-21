from __future__ import annotations

import hashlib
import random
import time
import traceback

from ..actors import actor_state
from ..behaviors import EgoRiskResponse
from ..behaviors.controllers import vehicle_controller
from ..carla_runtime import require_carla
from ..evaluation.risk import observe
from ..geometry.routes import RoadRoute
from ..math_utils import kmh_to_mps
from ..projection import actor_bbox_2d
from ..recording.recorder import EpisodeRecorder
from ..runtime.sensors import attach_sensors
from ..runtime.session import ActorScope, spawn_exact
from ..runtime.commands import apply_controls, initialize_motion
from ..video import create_video
from .models import ROLES
from .registry import get_scenario


def run_episode(session, config, layout, branch, directory, identity, fresh_world=False):
    random.seed(config["scenario"]["random_seed"])
    data = config
    recorder = EpisodeRecorder(directory, data, layout, {**identity, "branch": branch})
    scope, tracker, buffer = ActorScope(), None, None
    diagnostic_index = 0
    try:
        world = session.world if fresh_world else session.reset()
        road_map = world.get_map()
        if hashlib.sha256(road_map.to_opendrive().encode()).hexdigest() != layout["map_fingerprint"]:
            raise RuntimeError("Map changed after freezing the pair layout")
        actors, transforms = {}, {}
        for role, key in (("ego", "ego_spawn"), ("primary_risk_actor", "actor_spawn")):
            actors[role], transforms[role] = spawn_exact(world, layout["blueprints"][role], layout[key], role, scope)
        camera, buffer, tracker = attach_sensors(world, actors["ego"], data["recording"], scope)
        carla = require_carla()
        apply_controls(session.manager.client,actors,{role:carla.VehicleControl(brake=1.0) for role in actors})
        consecutive = 0
        # Drain warm-up images while the vehicles settle, before assigning road speed.
        for warmup in range(data["recording"]["warmup_frames"]):
            snapshot = session.tick()
            image = buffer.get(int(snapshot.frame), data["recording"]["image_timeout_seconds"])
            consecutive = consecutive+1 if image is not None else 0
        if consecutive < 3:
            raise RuntimeError("RGB camera failed warm-up synchronization")
        initialize_motion(session.manager.client,actors,transforms,
                          {"ego":kmh_to_mps(data["ego_vehicle"]["initial_speed_kmh"]),
                           "primary_risk_actor":kmh_to_mps(data["risk_actor"]["initial_speed_kmh"])})
        scenario = get_scenario(data["scenario"]["scenario_id"])
        scenario.initialize(data, layout, branch)
        road = RoadRoute(layout["ego_route"])
        dt = data["carla"]["fixed_delta_seconds"]
        controllers = {role: vehicle_controller(actors[role], dt, data, role) for role in ROLES}
        response = EgoRiskResponse(data["ego_vehicle"], dt)
        start_time = snapshot.timestamp.elapsed_seconds
        completed = False
        for index in range(round(data["recording"]["max_episode_seconds"]/dt)):
            states = {role: actor_state(actors[role], road_map, role) for role in ROLES}
            result = scenario.step(states, index)
            for event in result.events:
                recorder.event(event)
            controls = {}
            vehicle_controls = {}
            hazard = observe(states["ego"], states["primary_risk_actor"], road.forward(road.station(states["ego"].location)), data["risk_labelling"])
            if hazard["is_risk"] and response.trigger_index is None:
                response.trigger(index)
                recorder.event({"event": "ego_response_triggered", "step_index": index, "speed_mps": states["ego"].speed_mps})
            for role in ROLES:
                speed, target = result.targets[role]
                max_brake = result.brake_limits.get(role, 1.0)
                if role == "ego":
                    cruise = speed
                    speed = response.target_speed(index, states[role].speed_mps, cruise)
                    if speed < cruise:
                        max_brake = data["ego_vehicle"]["risk_max_brake"]
                control = controllers[role].run_step(speed, target, max_brake=max_brake)
                controls[role] = {"throttle": control.throttle, "brake": control.brake, "steer": control.steer,
                                  "gear": getattr(control, "gear", None),
                                  "manual_gear_shift": getattr(control, "manual_gear_shift", None),
                                  "target_speed_mps": speed}
                vehicle_controls[role] = control
            apply_controls(session.manager.client,actors,vehicle_controls)
            snapshot = session.tick()
            frame_id = int(snapshot.frame)
            states = {role: actor_state(actors[role], road_map, role) for role in ROLES}
            image = buffer.get(frame_id, data["recording"]["image_timeout_seconds"])
            risk = observe(states["ego"], states["primary_risk_actor"], road.forward(road.station(states["ego"].location)), data["risk_labelling"],
                           tracker.happened_at(frame_id), tracker.happened_by(frame_id))
            recording = data["recording"]
            boxes = actor_bbox_2d(actors["primary_risk_actor"], camera, recording["image_width"], recording["image_height"], recording["camera_fov"])
            recorder.append({**identity, "branch": branch, "step_index": index, "frame_id": frame_id,
                             "timestamp": float(snapshot.timestamp.elapsed_seconds),
                             "relative_time_seconds": float(snapshot.timestamp.elapsed_seconds-start_time),
                             "rgb_file": recorder.save_rgb(image) if image is not None else None,
                             "ego": states["ego"].as_dict(), "actors": [states["primary_risk_actor"].as_dict()],
                             "supporting_actors": [], "boxes_2d": {"primary_risk_actor": boxes}, "risk": risk,
                             "controls": controls, "maneuver_state": result.state,
                             "sensor": {"image_frame_id": int(image.frame) if image is not None else None}})
            for diagnostic in buffer.diagnostics[diagnostic_index:]:
                recorder.event(diagnostic)
            diagnostic_index = len(buffer.diagnostics)
            if result.complete:
                completed = True
                break
            if risk["collision_occurred"]:
                # A near-miss pair cannot pass after a collision, but retain the evidence.
                recorder.event({"event": "collision_terminated", "step_index": index})
                break
        time.sleep(recording["sensor_drain_seconds"])
        summary = recorder.finalize(tracker.events, "complete" if completed else "incomplete", None if completed else "maneuver/tail not completed")
    except BaseException as exc:
        recorder.event({"event": "exception", "type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()})
        summary = recorder.finalize(tracker.events if tracker else [], "failed", str(exc))
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
    finally:
        scope.close()
        recorder.close()
    if data["recording"].get("create_video") and recorder.frames:
        try:
            create_video(directory)
        except (RuntimeError, ValueError, OSError) as exc:
            from ..recording.recorder import write_json
            summary["video_error"] = str(exc)
            write_json(directory/"episode.json", summary)
    return summary
