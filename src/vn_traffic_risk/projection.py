from __future__ import annotations

import math
from typing import Any

import numpy as np


def camera_intrinsic(width: int, height: int, fov_degrees: float) -> np.ndarray:
    focal = width / (2.0 * math.tan(math.radians(fov_degrees) / 2.0))
    intrinsic = np.eye(3, dtype=np.float64)
    intrinsic[0, 0] = focal
    intrinsic[1, 1] = focal
    intrinsic[0, 2] = width / 2.0
    intrinsic[1, 2] = height / 2.0
    return intrinsic


def actor_bbox_2d(
    actor: Any,
    camera: Any,
    width: int,
    height: int,
    fov_degrees: float,
) -> list[float] | None:
    world_vertices = actor.bounding_box.get_world_vertices(actor.get_transform())
    if not world_vertices:
        return None
    world_to_camera = np.asarray(
        camera.get_transform().get_inverse_matrix(),
        dtype=np.float64,
    )
    intrinsic = camera_intrinsic(width, height, fov_degrees)
    pixels: list[tuple[float, float]] = []
    for vertex in world_vertices:
        world_point = np.array([vertex.x, vertex.y, vertex.z, 1.0], dtype=np.float64)
        unreal_camera = world_to_camera @ world_point
        # CARLA/UE: x forward, y right, z up. Camera: z forward, x right, y down.
        camera_point = np.array(
            [unreal_camera[1], -unreal_camera[2], unreal_camera[0]],
            dtype=np.float64,
        )
        if camera_point[2] <= 0.05:
            continue
        projected = intrinsic @ camera_point
        pixels.append((projected[0] / projected[2], projected[1] / projected[2]))
    if len(pixels) < 2:
        return None
    xs = [point[0] for point in pixels]
    ys = [point[1] for point in pixels]
    xmin = max(0.0, min(xs))
    ymin = max(0.0, min(ys))
    xmax = min(float(width - 1), max(xs))
    ymax = min(float(height - 1), max(ys))
    if xmin >= xmax or ymin >= ymax:
        return None
    return [round(xmin, 2), round(ymin, 2), round(xmax, 2), round(ymax, 2)]

