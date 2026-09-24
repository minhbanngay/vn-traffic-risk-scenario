import pytest

from vn_traffic_risk.math_utils import cubic_hermite_curve, interpolate_lane_change, polyline_length
from vn_traffic_risk.models import Vec3


def test_lane_change_has_exact_endpoints() -> None:
    start = Vec3(0.0, 0.0)
    end = Vec3(10.0, 3.5)
    points = interpolate_lane_change(start, end, 11)
    assert points[0] == start
    assert points[-1] == end
    assert all(points[index].x <= points[index + 1].x for index in range(10))


def test_polyline_length() -> None:
    points = [Vec3(0, 0), Vec3(3, 4), Vec3(6, 8)]
    assert polyline_length(points) == pytest.approx(10.0)


def test_hermite_curve_has_exact_endpoints() -> None:
    start = Vec3(0.0, 0.0)
    end = Vec3(10.0, 3.5)
    points = cubic_hermite_curve(
        start,
        end,
        Vec3(1.0, 0.0),
        Vec3(1.0, 0.0),
        samples=15,
        tangent_scale=8.0,
    )
    assert points[0] == start
    assert points[-1] == end
