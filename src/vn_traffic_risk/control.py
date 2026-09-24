from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .carla_runtime import require_carla
from .math_utils import clamp, distance_2d, kmh_to_mps, wrap_angle_radians
from .models import Vec3


class PolylineFollower:
    def __init__(self, points: list[Vec3], reach_threshold_m: float = 2.5) -> None:
        if len(points) < 2:
            raise ValueError("A route requires at least two points")
        self.points = points
        self.index = 1
        self.reach_threshold_m = reach_threshold_m

    def update(self, location: Vec3) -> Vec3:
        while self.index < len(self.points) - 1:
            if distance_2d(location, self.points[self.index]) > self.reach_threshold_m:
                break
            self.index += 1
        return self.points[self.index]

    @property
    def finished(self) -> bool:
        return self.index >= len(self.points) - 1

    def remaining_distance_to(self, location: Vec3, target_index: int) -> float:
        if self.index > target_index:
            return -distance_2d(location, self.points[target_index])
        total = distance_2d(location, self.points[self.index])
        for first, second in zip(
            self.points[self.index:target_index],
            self.points[self.index + 1:target_index + 1],
        ):
            total += distance_2d(first, second)
        return total


class EgoRiskResponse:
    """Temporary speed reduction followed by automatic recovery."""

    def __init__(self, config: dict[str, Any], fixed_delta_seconds: float) -> None:
        self.dt = fixed_delta_seconds
        self.delay_frames = round(
            float(config["reaction_delay_seconds"]) / fixed_delta_seconds
        )
        self.hold_frames = round(
            float(config["risk_slowdown_hold_seconds"]) / fixed_delta_seconds
        )
        self.max_slowdown_frames = round(
            float(config["risk_slowdown_max_seconds"]) / fixed_delta_seconds
        )
        self.slowdown_speed_mps = kmh_to_mps(
            float(config["risk_slowdown_speed_kmh"])
        )
        self.trigger_index: int | None = None
        self.slowdown_start_index: int | None = None
        self.hold_start_index: int | None = None
        self.recovered = False

    def trigger(self, step_index: int) -> None:
        if self.trigger_index is None:
            self.trigger_index = step_index

    def target_speed(
        self,
        step_index: int,
        current_speed_mps: float,
        cruise_speed_mps: float,
    ) -> float:
        if self.trigger_index is None or self.recovered:
            return cruise_speed_mps
        if step_index - self.trigger_index < self.delay_frames:
            return cruise_speed_mps

        if self.slowdown_start_index is None:
            self.slowdown_start_index = step_index

        reached_slow_speed = current_speed_mps <= self.slowdown_speed_mps + 0.35
        timed_out = (
            step_index - self.slowdown_start_index >= self.max_slowdown_frames
        )
        if self.hold_start_index is None and (reached_slow_speed or timed_out):
            self.hold_start_index = step_index

        if self.hold_start_index is not None:
            if step_index - self.hold_start_index >= self.hold_frames:
                self.recovered = True
                return cruise_speed_mps
        return min(cruise_speed_mps, self.slowdown_speed_mps)


@dataclass
class ControllerGains:
    speed_kp: float = 0.55
    speed_ki: float = 0.08
    heading_kp: float = 1.35
    heading_kd: float = 0.10


class SimpleVehicleController:
    """Small speed-PID + heading controller with no dependency on CARLA agents."""

    def __init__(self, vehicle: Any, fixed_delta_seconds: float, gains: ControllerGains | None = None) -> None:
        self.vehicle = vehicle
        self.dt = fixed_delta_seconds
        self.gains = gains or ControllerGains()
        self.speed_integral = 0.0
        self.previous_heading_error = 0.0

    def run_step(
        self,
        target_speed_mps: float,
        target: Vec3,
        brake_override: float = 0.0,
        max_brake: float = 1.0,
    ) -> Any:
        carla = require_carla()
        transform = self.vehicle.get_transform()
        velocity = self.vehicle.get_velocity()
        speed = math.sqrt(velocity.x ** 2 + velocity.y ** 2 + velocity.z ** 2)

        dx = target.x - transform.location.x
        dy = target.y - transform.location.y
        desired_heading = math.atan2(dy, dx)
        current_heading = math.radians(transform.rotation.yaw)
        heading_error = wrap_angle_radians(desired_heading - current_heading)
        derivative = (heading_error - self.previous_heading_error) / max(self.dt, 1e-3)
        self.previous_heading_error = heading_error
        steer = clamp(
            self.gains.heading_kp * heading_error + self.gains.heading_kd * derivative,
            -1.0,
            1.0,
        )

        speed_error = target_speed_mps - speed
        self.speed_integral = clamp(self.speed_integral + speed_error * self.dt, -10.0, 10.0)
        command = self.gains.speed_kp * speed_error + self.gains.speed_ki * self.speed_integral
        throttle = clamp(command, 0.0, 1.0)
        brake = clamp(-command, 0.0, 1.0)
        if brake_override > 0.0:
            throttle = 0.0
            brake = max(brake, clamp(brake_override, 0.0, 1.0))
        brake = min(brake, clamp(max_brake, 0.0, 1.0))
        return carla.VehicleControl(
            throttle=float(throttle),
            steer=float(steer),
            brake=float(brake),
            hand_brake=False,
            reverse=False,
        )


class CutInSynchronizer:
    def __init__(self, config: dict[str, Any]) -> None:
        self.time_offset = float(config["runtime"]["target_time_offset_seconds"])
        actor_cfg = config["risk_actor"]
        self.cruise_mps = kmh_to_mps(float(actor_cfg["target_speed_kmh"]))
        self.min_mps = kmh_to_mps(float(actor_cfg["min_speed_kmh"]))
        self.max_mps = kmh_to_mps(float(actor_cfg["max_speed_kmh"]))
        self.smoothed_target_mps = self.cruise_mps

    def target_speed(
        self,
        ego_eta_seconds: float | None,
        actor_distance_to_merge_m: float,
        after_merge: bool,
    ) -> float:
        if after_merge or ego_eta_seconds is None or actor_distance_to_merge_m < 0.0:
            raw = self.cruise_mps
        else:
            desired_eta = max(0.35, ego_eta_seconds + self.time_offset)
            raw = actor_distance_to_merge_m / desired_eta
            raw = clamp(raw, self.min_mps, self.max_mps)
        self.smoothed_target_mps = 0.85 * self.smoothed_target_mps + 0.15 * raw
        return self.smoothed_target_mps
