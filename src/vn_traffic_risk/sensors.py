from __future__ import annotations

import queue
import threading
import time
from typing import Any

from .carla_runtime import require_carla


class RGBFrameBuffer:
    def __init__(self) -> None:
        self._queue: queue.Queue[Any] = queue.Queue()

    def callback(self, image: Any) -> None:
        self._queue.put(image)

    def get(self, frame_id: int, timeout_seconds: float) -> Any | None:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            try:
                image = self._queue.get(timeout=max(0.01, deadline - time.monotonic()))
            except queue.Empty:
                return None
            if int(image.frame) == frame_id:
                return image
            if int(image.frame) > frame_id:
                self._queue.put(image)
                return None
        return None


class CollisionTracker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: list[dict[str, Any]] = []
        self._frames: set[int] = set()

    def callback(self, event: Any) -> None:
        record = {
            "frame": int(event.frame),
            "timestamp": float(event.timestamp),
            "actor_id": int(event.actor.id),
            "other_actor_id": int(event.other_actor.id),
            "other_actor_type": str(event.other_actor.type_id),
            "normal_impulse": {
                "x": float(event.normal_impulse.x),
                "y": float(event.normal_impulse.y),
                "z": float(event.normal_impulse.z),
            },
        }
        with self._lock:
            self._events.append(record)
            self._frames.add(int(event.frame))

    def happened_at(self, frame_id: int) -> bool:
        with self._lock:
            return frame_id in self._frames

    def happened_by(self, frame_id: int) -> bool:
        """Remain true after the first event, including if the callback arrives late."""
        with self._lock:
            return any(event_frame <= frame_id for event_frame in self._frames)

    @property
    def events(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._events)


def attach_rgb_camera(world: Any, ego: Any, config: dict[str, Any]) -> tuple[Any, RGBFrameBuffer]:
    carla = require_carla()
    blueprint = world.get_blueprint_library().find("sensor.camera.rgb")
    blueprint.set_attribute("image_size_x", str(int(config["image_width"])))
    blueprint.set_attribute("image_size_y", str(int(config["image_height"])))
    blueprint.set_attribute("fov", str(float(config["camera_fov"])))
    blueprint.set_attribute("sensor_tick", str(float(config["camera_tick_seconds"])))
    # Start from manual_control.py's bound-relative first-person transform, but
    # move it rearward for a visible hood on long vehicles such as Model 3.
    bound_x = 0.5 + float(ego.bounding_box.extent.x)
    bound_z = 0.5 + float(ego.bounding_box.extent.z)
    transform = carla.Transform(
        carla.Location(
            x=float(config.get("camera_x_bound_factor", 0.35)) * bound_x,
            z=float(config.get("camera_z_bound_factor", 1.15)) * bound_z,
        ),
        carla.Rotation(pitch=float(config.get("camera_pitch_degrees", -5.0))),
    )
    sensor = world.spawn_actor(
        blueprint,
        transform,
        attach_to=ego,
        attachment_type=carla.AttachmentType.Rigid,
    )
    buffer = RGBFrameBuffer()
    sensor.listen(buffer.callback)
    return sensor, buffer


def attach_collision_sensor(world: Any, ego: Any) -> tuple[Any, CollisionTracker]:
    carla = require_carla()
    blueprint = world.get_blueprint_library().find("sensor.other.collision")
    sensor = world.spawn_actor(blueprint, carla.Transform(), attach_to=ego)
    tracker = CollisionTracker()
    sensor.listen(tracker.callback)
    return sensor, tracker
