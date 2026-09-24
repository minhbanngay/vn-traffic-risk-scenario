from __future__ import annotations

import math
from collections.abc import Sequence

from .models import Vec3


EPSILON = 1e-6


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def kmh_to_mps(value: float) -> float:
    return value / 3.6


def mps_to_kmh(value: float) -> float:
    return value * 3.6


def norm2(x: float, y: float) -> float:
    return math.hypot(x, y)


def distance_2d(a: Vec3, b: Vec3) -> float:
    return norm2(a.x - b.x, a.y - b.y)


def wrap_angle_radians(angle: float) -> float:
    return (angle + math.pi) % (2.0 * math.pi) - math.pi


def polyline_length(points: Sequence[Vec3], start_index: int = 0) -> float:
    if len(points) < 2 or start_index >= len(points) - 1:
        return 0.0
    total = 0.0
    for first, second in zip(points[start_index:], points[start_index + 1:]):
        total += distance_2d(first, second)
    return total


def cubic_smoothstep(t: float) -> float:
    t = clamp(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def interpolate_lane_change(
    start: Vec3,
    end: Vec3,
    samples: int,
) -> list[Vec3]:
    """Generate a smooth lateral transition without teleporting the actor."""
    if samples < 2:
        raise ValueError("samples must be at least 2")
    points: list[Vec3] = []
    for index in range(samples):
        ratio = index / (samples - 1)
        smooth = cubic_smoothstep(ratio)
        points.append(
            Vec3(
                x=start.x + (end.x - start.x) * ratio,
                y=start.y + (end.y - start.y) * smooth,
                z=start.z + (end.z - start.z) * ratio,
            )
        )
    return points


def cubic_hermite_curve(
    start: Vec3,
    end: Vec3,
    start_tangent: Vec3,
    end_tangent: Vec3,
    samples: int,
    tangent_scale: float,
) -> list[Vec3]:
    """Smooth curve whose endpoint headings follow the two lane directions."""
    if samples < 2:
        raise ValueError("samples must be at least 2")
    points: list[Vec3] = []
    for index in range(samples):
        t = index / (samples - 1)
        t2 = t * t
        t3 = t2 * t
        h00 = 2 * t3 - 3 * t2 + 1
        h10 = t3 - 2 * t2 + t
        h01 = -2 * t3 + 3 * t2
        h11 = t3 - t2
        points.append(
            Vec3(
                x=h00 * start.x + h10 * tangent_scale * start_tangent.x
                + h01 * end.x + h11 * tangent_scale * end_tangent.x,
                y=h00 * start.y + h10 * tangent_scale * start_tangent.y
                + h01 * end.y + h11 * tangent_scale * end_tangent.y,
                z=start.z + (end.z - start.z) * t,
            )
        )
    return points
