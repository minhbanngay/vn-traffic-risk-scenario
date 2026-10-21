from __future__ import annotations

import threading
import time

from ..carla_runtime import require_carla
from ..sensors import CollisionTracker


class RGBFrameBuffer:
    """Preserves future frames and records receipt/timeout diagnostics."""
    def __init__(self):
        self.condition = threading.Condition()
        self.images = {}
        self.seen = set()
        self.diagnostics = []

    def callback(self, image):
        with self.condition:
            duplicate = image.frame in self.seen
            self.seen.add(int(image.frame))
            self.images[int(image.frame)] = image
            self.diagnostics.append({"event": "rgb_received", "frame_id": int(image.frame), "duplicate": duplicate})
            self.condition.notify_all()

    def get(self, frame_id, timeout_seconds):
        deadline = time.monotonic()+timeout_seconds
        with self.condition:
            while frame_id not in self.images:
                remaining = deadline-time.monotonic()
                if remaining <= 0:
                    self.diagnostics.append({"event": "rgb_timeout", "frame_id": frame_id})
                    return None
                self.condition.wait(remaining)
            for old in [k for k in self.images if k < frame_id]:
                del self.images[old]
            return self.images.pop(frame_id)


def attach_sensors(world, ego, config, scope):
    carla = require_carla()
    library = world.get_blueprint_library()
    collision_sensor = scope.add(world.spawn_actor(library.find("sensor.other.collision"), carla.Transform(), attach_to=ego))
    tracker = CollisionTracker()
    collision_sensor.listen(tracker.callback)
    bp = library.find("sensor.camera.rgb")
    for name, value in (("image_size_x", config["image_width"]), ("image_size_y", config["image_height"]),
                        ("fov", config["camera_fov"]), ("sensor_tick", config["camera_tick_seconds"])):
        bp.set_attribute(name, str(value))
    transform = carla.Transform(carla.Location(x=config["camera_x_bound_factor"]*(0.5+ego.bounding_box.extent.x),
                                              z=config["camera_z_bound_factor"]*(0.5+ego.bounding_box.extent.z)),
                                carla.Rotation(pitch=config["camera_pitch_degrees"]))
    camera = scope.add(world.spawn_actor(bp, transform, attach_to=ego, attachment_type=carla.AttachmentType.Rigid))
    buffer = RGBFrameBuffer()
    camera.listen(buffer.callback)
    return camera, buffer, tracker
