from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class ConfigError(ValueError):
    """Raised when a scenario configuration is incomplete or inconsistent."""


@dataclass(frozen=True)
class ResolvedConfig:
    data: dict[str, Any]
    source_path: Path

    @property
    def scenario_id(self) -> str:
        return str(self.data["scenario"]["scenario_id"])

    @property
    def episode_id(self) -> str:
        return str(self.data["scenario"]["episode_id"])

    @property
    def variant(self) -> str:
        return str(self.data["scenario"]["variant"])

    @property
    def fixed_delta_seconds(self) -> float:
        return float(self.data["carla"]["fixed_delta_seconds"])

    @property
    def output_directory(self) -> Path:
        output_root = Path(self.data["recording"]["output_root"])
        if not output_root.is_absolute():
            output_root = self.source_path.parent.parent.parent / output_root
        return output_root / self.scenario_id / self.episode_id / self.variant


def _require(mapping: dict[str, Any], dotted_key: str) -> Any:
    value: Any = mapping
    for part in dotted_key.split("."):
        if not isinstance(value, dict) or part not in value:
            raise ConfigError(f"Missing required configuration key: {dotted_key}")
        value = value[part]
    return value


def _validate(config: dict[str, Any]) -> None:
    required = (
        "scenario.scenario_id",
        "scenario.episode_id",
        "scenario.variant",
        "carla.host",
        "carla.port",
        "carla.map",
        "carla.fixed_delta_seconds",
        "placement.mode",
        "placement.ego_distance_to_merge_m",
        "placement.actor_start_behind_ego_m",
        "ego_vehicle.blueprint",
        "risk_actor.blueprint_candidates",
        "risk_labelling.horizon",
        "risk_labelling.horizon_step_seconds",
        "recording.output_root",
        "recording.max_episode_seconds",
    )
    for key in required:
        _require(config, key)

    if config["placement"]["mode"] != "automatic_adjacent_lanes":
        raise ConfigError(
            "This starter project currently supports placement.mode="
            "'automatic_adjacent_lanes' only."
        )
    if float(config["carla"]["fixed_delta_seconds"]) <= 0:
        raise ConfigError("carla.fixed_delta_seconds must be positive")
    if int(config["risk_labelling"]["horizon"]) <= 0:
        raise ConfigError("risk_labelling.horizon must be positive")
    if not config["risk_actor"]["blueprint_candidates"]:
        raise ConfigError("risk_actor.blueprint_candidates cannot be empty")
    if str(config["placement"].get("lane_change_side", "")).lower() != "left":
        raise ConfigError(
            "This scenario requires placement.lane_change_side='left' so the "
            "motorcycle merges right into the ego lane"
        )
    if float(config["placement"]["actor_start_behind_ego_m"]) <= 0:
        raise ConfigError("placement.actor_start_behind_ego_m must be positive")
    slowdown_speed = float(config["ego_vehicle"].get("risk_slowdown_speed_kmh", 0.0))
    cruise_speed = float(config["ego_vehicle"]["target_speed_kmh"])
    if not 0 < slowdown_speed < cruise_speed:
        raise ConfigError(
            "ego_vehicle.risk_slowdown_speed_kmh must be positive and below "
            "ego_vehicle.target_speed_kmh"
        )
    risk_max_brake = float(config["ego_vehicle"].get("risk_max_brake", 1.0))
    if not 0 < risk_max_brake <= 1:
        raise ConfigError("ego_vehicle.risk_max_brake must be in the range (0, 1]")

    recording = config["recording"]
    image_format = str(recording.get("image_format", "png")).lower()
    if image_format not in {"png", "jpg", "jpeg"}:
        raise ConfigError("recording.image_format must be png, jpg, or jpeg")
    jpeg_quality = int(recording.get("jpeg_quality", 85))
    if not 1 <= jpeg_quality <= 100:
        raise ConfigError("recording.jpeg_quality must be between 1 and 100")


def load_config(path: str | Path, variant_override: str | None = None) -> ResolvedConfig:
    source_path = Path(path).expanduser().resolve()
    with source_path.open("r", encoding="utf-8") as stream:
        loaded = yaml.safe_load(stream)
    if not isinstance(loaded, dict):
        raise ConfigError("The YAML root must be a mapping")

    config = copy.deepcopy(loaded)
    variant = variant_override or str(config.get("scenario", {}).get("variant", "risk"))
    profiles = config.get("variant_profiles", {})
    if variant not in profiles:
        raise ConfigError(
            f"Unknown variant '{variant}'. Available variants: {sorted(profiles)}"
        )
    profile = profiles[variant]
    config["scenario"]["variant"] = variant
    config["scenario"]["interaction_type"] = profile["interaction_type"]
    config["ego_vehicle"]["reaction"] = profile["ego_reaction"]
    config.setdefault("runtime", {})["target_time_offset_seconds"] = float(
        profile["target_time_offset_seconds"]
    )

    _validate(config)
    return ResolvedConfig(config, source_path)
