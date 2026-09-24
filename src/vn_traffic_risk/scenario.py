from __future__ import annotations

import random
import time
from pathlib import Path
from typing import Any

from .actors import actor_state, set_forward_speed, spawn_vehicle, stop_and_destroy
from .carla_runtime import WorldManager
from .config import ResolvedConfig
from .control import (
    CutInSynchronizer,
    EgoRiskResponse,
    PolylineFollower,
    SimpleVehicleController,
)
from .math_utils import kmh_to_mps
from .models import FrameRecord, Vec3
from .placement import build_automatic_cut_in_layout
from .projection import actor_bbox_2d
from .recorder import EpisodeRecorder
from .risk import evaluate_risk, safe_eta
from .sensors import attach_collision_sensor, attach_rgb_camera


def _location(actor: Any) -> Vec3:
    location = actor.get_location()
    return Vec3(float(location.x), float(location.y), float(location.z))


def run_scenario(config: ResolvedConfig) -> tuple[Path, dict[str, Any]]:
    data = config.data
    random.seed(int(data["scenario"]["random_seed"]))
    manager = WorldManager(data["carla"])
    managed_actors: list[Any] = []
    world = None
    try:
        world = manager.connect()
        manager.apply_weather(str(data["environment"]["weather"]))
        road_map = world.get_map()
        layout = build_automatic_cut_in_layout(road_map, data["placement"])

        ego = spawn_vehicle(
            world,
            data["ego_vehicle"]["blueprint"],
            layout.ego_spawn_transform,
            str(data["ego_vehicle"]["role_name"]),
        )
        risk_actor = spawn_vehicle(
            world,
            data["risk_actor"]["blueprint_candidates"],
            layout.actor_spawn_transform,
            str(data["risk_actor"]["role_name"]),
        )
        managed_actors.extend([ego, risk_actor])
        set_forward_speed(
            ego,
            layout.ego_spawn_transform,
            kmh_to_mps(float(data["ego_vehicle"]["initial_speed_kmh"])),
        )
        set_forward_speed(
            risk_actor,
            layout.actor_spawn_transform,
            kmh_to_mps(float(data["risk_actor"]["initial_speed_kmh"])),
        )

        collision_sensor, collision_tracker = attach_collision_sensor(world, ego)
        managed_actors.append(collision_sensor)
        camera = None
        image_buffer = None
        if bool(data["recording"]["save_rgb"]):
            camera, image_buffer = attach_rgb_camera(world, ego, data["recording"])
            managed_actors.append(camera)

        ego_follower = PolylineFollower(layout.ego_route)
        actor_follower = PolylineFollower(layout.actor_route)
        ego_controller = SimpleVehicleController(ego, config.fixed_delta_seconds)
        actor_controller = SimpleVehicleController(risk_actor, config.fixed_delta_seconds)
        synchronizer = CutInSynchronizer(data)
        ego_response = EgoRiskResponse(data["ego_vehicle"], config.fixed_delta_seconds)
        recorder = EpisodeRecorder(config, layout.description)

        ego_target_speed = kmh_to_mps(float(data["ego_vehicle"]["target_speed_kmh"]))
        max_steps = round(
            float(data["recording"]["max_episode_seconds"])
            / config.fixed_delta_seconds
        )
        post_merge_frames = round(
            float(data["placement"].get("post_merge_recording_seconds", 3.0))
            / config.fixed_delta_seconds
        )
        risk_first_index: int | None = None
        collision_index: int | None = None
        merge_completed_index: int | None = None

        for step_index in range(max_steps):
            ego_location = _location(ego)
            actor_location = _location(risk_actor)
            ego_target = ego_follower.update(ego_location)
            actor_target = actor_follower.update(actor_location)

            ego_pre_state = actor_state(ego, road_map, "ego")
            ego_distance_pre = ego_follower.remaining_distance_to(
                ego_pre_state.location,
                layout.ego_merge_index,
            )
            actor_distance_pre = actor_follower.remaining_distance_to(
                actor_location,
                layout.actor_merge_end_index,
            )
            # At startup both vehicles are nearly stationary. A live ETA would
            # be extremely large and hold the motorcycle back, so synchronize
            # against at least the ego's configured cruise speed.
            ego_eta = safe_eta(
                ego_distance_pre,
                max(ego_pre_state.speed_mps, ego_target_speed),
            )
            actor_target_speed = synchronizer.target_speed(
                ego_eta,
                actor_distance_pre,
                after_merge=actor_follower.index > layout.actor_merge_end_index,
            )

            effective_ego_target_speed = ego_target_speed
            if data["ego_vehicle"]["reaction"] == "brake_on_risk":
                effective_ego_target_speed = ego_response.target_speed(
                    step_index,
                    ego_pre_state.speed_mps,
                    ego_target_speed,
                )
            ego_max_brake = 1.0
            if effective_ego_target_speed < ego_target_speed:
                ego_max_brake = float(data["ego_vehicle"]["risk_max_brake"])
            ego.apply_control(
                ego_controller.run_step(
                    effective_ego_target_speed,
                    ego_target,
                    max_brake=ego_max_brake,
                )
            )
            risk_actor.apply_control(
                actor_controller.run_step(actor_target_speed, actor_target)
            )

            snapshot = manager.tick()
            frame_id = int(snapshot.frame)
            timestamp = float(snapshot.timestamp.elapsed_seconds)
            ego_state_now = actor_state(ego, road_map, "ego")
            actor_state_now = actor_state(risk_actor, road_map, "risk_actor")
            ego_follower.update(ego_state_now.location)
            actor_follower.update(actor_state_now.location)
            ego_distance = ego_follower.remaining_distance_to(
                ego_state_now.location,
                layout.ego_merge_index,
            )
            actor_distance = actor_follower.remaining_distance_to(
                actor_state_now.location,
                layout.actor_merge_end_index,
            )
            collision = collision_tracker.happened_by(frame_id)
            if collision and collision_index is None:
                collision_index = step_index
            maneuver_active = (
                actor_follower.index >= layout.actor_merge_start_index
                and actor_distance >= -12.0
            )
            risk = evaluate_risk(
                ego=ego_state_now,
                actor=actor_state_now,
                ego_distance_to_merge_m=ego_distance,
                actor_distance_to_merge_m=actor_distance,
                maneuver_active=maneuver_active,
                collision=collision,
                interaction_type=str(data["scenario"]["interaction_type"]),
                thresholds=data["risk_labelling"],
            )
            if risk.is_risk and risk_first_index is None:
                risk_first_index = step_index
                ego_response.trigger(step_index)

            if (
                merge_completed_index is None
                and actor_follower.index > layout.actor_merge_end_index
            ):
                merge_completed_index = step_index

            rgb_file = None
            if image_buffer is not None:
                image = image_buffer.get(
                    frame_id,
                    float(data["recording"]["image_timeout_seconds"]),
                )
                if image is not None:
                    rgb_file = recorder.save_rgb(image)

            boxes: dict[str, list[float] | None] = {}
            if camera is not None and bool(data["recording"]["save_2d_boxes"]):
                boxes[str(risk_actor.id)] = actor_bbox_2d(
                    risk_actor,
                    camera,
                    int(data["recording"]["image_width"]),
                    int(data["recording"]["image_height"]),
                    float(data["recording"]["camera_fov"]),
                )
            recorder.append(
                FrameRecord(
                    frame_id=frame_id,
                    timestamp=timestamp,
                    rgb_file=rgb_file,
                    ego=ego_state_now,
                    actors=[actor_state_now],
                    boxes_2d=boxes,
                    risk=risk,
                )
            )

            if collision_index is not None and step_index - collision_index >= round(1.0 / config.fixed_delta_seconds):
                break
            if (
                config.variant == "risk"
                and merge_completed_index is not None
                and step_index - merge_completed_index >= post_merge_frames
            ):
                break
            if actor_follower.finished:
                break

        # Give asynchronous sensor callbacks a brief chance to finish before finalization.
        time.sleep(0.05)
        summary = recorder.finalize(collision_tracker.events)
        return recorder.output_dir, summary
    finally:
        stop_and_destroy(managed_actors)
        manager.restore()
