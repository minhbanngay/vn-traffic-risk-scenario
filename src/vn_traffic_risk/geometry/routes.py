from __future__ import annotations

import math
from bisect import bisect_right

from ..models import Vec3


class RoadRoute:
    """Arc-length route with continuous projection and a signed lateral offset."""

    def __init__(self, points: list[dict]):
        self.points = [Vec3(**p) for p in points]
        if len(self.points) < 2:
            raise ValueError("Route requires at least two points")
        self.lengths = [0.0]
        for a, b in zip(self.points, self.points[1:]):
            self.lengths.append(self.lengths[-1] + math.hypot(b.x-a.x, b.y-a.y))

    @property
    def length(self) -> float:
        return self.lengths[-1]

    def at(self, station: float, lateral: float = 0.0) -> Vec3:
        i = min(len(self.points)-2, max(0, bisect_right(self.lengths, station)-1))
        a, b = self.points[i:i+2]
        span = max(1e-6, self.lengths[i+1]-self.lengths[i])
        t = (station-self.lengths[i])/span
        fx, fy = (b.x-a.x)/span, (b.y-a.y)/span
        return Vec3(a.x+t*(b.x-a.x)-fy*lateral, a.y+t*(b.y-a.y)+fx*lateral, a.z+t*(b.z-a.z))

    def station(self, point: Vec3) -> float:
        candidates = []
        for i, (a, b) in enumerate(zip(self.points, self.points[1:])):
            dx, dy = b.x-a.x, b.y-a.y
            span2 = dx*dx+dy*dy
            ratio = ((point.x-a.x)*dx+(point.y-a.y)*dy)/max(span2, 1e-6)
            if i != 0:
                ratio = max(0, ratio)
            if i != len(self.points)-2:
                ratio = min(1, ratio)
            distance = (point.x-a.x-ratio*dx)**2+(point.y-a.y-ratio*dy)**2
            candidates.append((distance, self.lengths[i]+ratio*math.sqrt(span2)))
        return min(candidates)[1]

    def forward(self, station: float) -> tuple[float, float]:
        a, b = self.at(station), self.at(station+0.5)
        norm = max(1e-6, math.hypot(b.x-a.x, b.y-a.y))
        return (b.x-a.x)/norm, (b.y-a.y)/norm

    def lateral(self, point: Vec3) -> float:
        station = self.station(point)
        center = self.at(station)
        fx, fy = self.forward(station)
        return -(point.x-center.x)*fy+(point.y-center.y)*fx
