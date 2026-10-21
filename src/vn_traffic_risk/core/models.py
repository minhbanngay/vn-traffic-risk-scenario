from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from ..models import ActorState, Vec3


@dataclass
class ScenarioStep:
    targets: dict[str, tuple[float, Any]]
    state: str
    events: list[dict] = field(default_factory=list)
    complete: bool = False
    brake_limits: dict[str, float] = field(default_factory=dict)


class Scenario(Protocol):
    def plan(self, world: Any, config: dict) -> dict: ...
    def freeze_intervention(self, session: Any, config: dict, layout: dict) -> dict: ...
    def initialize(self, config: dict, layout: dict, branch: str) -> None: ...
    def step(self, states: dict[str, ActorState], step_index: int) -> ScenarioStep: ...


ROLES = ("ego", "primary_risk_actor")


def decode_actor(value: dict) -> ActorState:
    vector_fields = {"location", "rotation", "velocity", "acceleration", "bbox_extent", "bbox_offset", "bbox_rotation"}
    return ActorState(**{key: Vec3(**item) if key in vector_fields else item for key, item in value.items()})
