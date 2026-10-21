from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class Vec3:
    x: float
    y: float
    z: float = 0.0

    def as_dict(self) -> dict[str, float]:
        return asdict(self)


@dataclass(frozen=True)
class ActorState:
    actor_id: int
    role_name: str
    type_id: str
    location: Vec3
    rotation: Vec3
    velocity: Vec3
    acceleration: Vec3
    speed_mps: float
    road_id: int | None
    lane_id: int | None
    bbox_extent: Vec3
    bbox_offset: Vec3 = Vec3(0.0, 0.0, 0.0)
    bbox_rotation: Vec3 = Vec3(0.0, 0.0, 0.0)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RiskObservation:
    is_risk: bool
    interaction_type: str
    risk_actor_id: int
    distance_m: float
    eta_ego_seconds: float | None
    eta_actor_seconds: float | None
    eta_difference_seconds: float | None
    closest_approach_time_seconds: float | None
    closest_approach_distance_m: float | None
    collision: bool
    reasons: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["reasons"] = list(self.reasons)
        return result


@dataclass
class FrameRecord:
    frame_id: int
    timestamp: float
    rgb_file: str | None
    ego: ActorState
    actors: list[ActorState]
    boxes_2d: dict[str, list[float] | None]
    risk: RiskObservation
    future_risk_vector: list[int] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "frame_id": self.frame_id,
            "timestamp": self.timestamp,
            "rgb_file": self.rgb_file,
            "ego": self.ego.as_dict(),
            "actors": [actor.as_dict() for actor in self.actors],
            "boxes_2d": self.boxes_2d,
            "risk": self.risk.as_dict(),
            "future_risk_vector": self.future_risk_vector,
        }

