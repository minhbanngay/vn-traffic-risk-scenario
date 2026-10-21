from __future__ import annotations

import copy
import hashlib
import json
import math
import sys
from importlib import metadata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from ..config import ConfigError


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def read_yaml(path: str | Path) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as stream:
        result = yaml.safe_load(stream)
    if not isinstance(result, dict):
        raise ConfigError(f"Expected YAML mapping: {path}")
    return result


def merge(base: dict, override: dict) -> dict:
    result = copy.deepcopy(base)
    for key, value in override.items():
        result[key] = merge(result[key], value) if isinstance(value, dict) and isinstance(result.get(key), dict) else copy.deepcopy(value)
    return result


def fingerprint(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def implementation_fingerprint() -> str:
    package = Path(__file__).resolve().parents[1]
    sources = {path.relative_to(package).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
               for path in sorted(package.rglob("*.py"))}
    return fingerprint(sources)


def runtime_environment() -> dict:
    versions = {}
    for name in ("carla","numpy","Pillow","PyYAML","imageio-ffmpeg"):
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = None
    binaries = {}
    try:
        distribution = metadata.distribution("carla")
        for file in distribution.files or []:
            if str(file).endswith((".pyd",".so")):
                binaries[str(file)] = hashlib.sha256(distribution.locate_file(file).read_bytes()).hexdigest()
    except metadata.PackageNotFoundError:
        pass
    return {"python":sys.version,"platform":sys.platform,"packages":versions,"carla_binaries":binaries}


@dataclass(frozen=True)
class PairConfig:
    data: dict[str, Any]
    source: Path
    root: Path

    @property
    def output_root(self) -> Path:
        path = Path(self.data["recording"]["output_root"])
        return path if path.is_absolute() else self.root / path

    @property
    def pair_id(self) -> str:
        return "P-" + fingerprint(self.data)[:12]

    def branch(self, name: str) -> dict:
        if name not in ("R", "CF"):
            raise ConfigError(f"Unknown branch: {name}")
        return {**copy.deepcopy(self.data), "branch": name, "intervention": copy.deepcopy(self.data["interventions"][name])}


def validate(data: dict) -> None:
    try:
        from .registry import INTERVENTION_MODES
        scenario_id = data["scenario"]["scenario_id"]
        if data["schema_version"] != 2 or scenario_id not in INTERVENTION_MODES:
            raise ConfigError("Requires schema_version=2 and an implemented scenario")
        if not data["carla"]["synchronous_mode"] or data["carla"].get("no_rendering_mode"):
            raise ConfigError("Paired collection requires synchronous rendering")
        server_fps = float(data["carla"].get("server_max_fps",20))
        if not math.isfinite(server_fps) or server_fps <= 0:
            raise ConfigError("server_max_fps must be finite and positive")
        health = data["carla"].get("health_monitor",{})
        if health.get("enabled"):
            interval = float(health["interval_seconds"])
            temperature = float(health["max_gpu_temperature_c"])
            vram = float(health["max_vram_fraction"])
            errors = health["max_probe_errors"]
            if not all(math.isfinite(v) for v in (interval,temperature,vram)) or not 0 < interval <= 30 or not 0 < temperature <= 95 or not 0 < vram <= 1:
                raise ConfigError("Invalid runtime health guard settings")
            if not isinstance(errors,int) or isinstance(errors,bool) or errors < 1:
                raise ConfigError("max_probe_errors must be a positive integer")
        positive = [data["carla"]["fixed_delta_seconds"], data["risk_actor"]["initial_speed_kmh"],
                    data["ego_vehicle"]["initial_speed_kmh"], data["ego_vehicle"]["target_speed_kmh"],
                    data["placement"]["actor_start_ahead_ego_m" if scenario_id == "INT-08" else "actor_start_behind_ego_m"], data["placement"]["minimum_route_length_m"],
                    data["placement"]["route_spacing_m"],
                    data["recording"]["max_episode_seconds"], data["recording"]["image_timeout_seconds"],
                    data["risk_labelling"]["horizon_step_seconds"]]
        if any(not math.isfinite(float(x)) or float(x) <= 0 for x in positive):
            raise ConfigError("Distances, speeds and time steps must be finite and positive")
        dt = float(data["carla"]["fixed_delta_seconds"])
        if abs(float(data["recording"]["camera_tick_seconds"]) - dt) > 1e-8:
            raise ConfigError("v2 requires camera_tick_seconds == fixed_delta_seconds")
        stride = float(data["risk_labelling"]["horizon_step_seconds"]) / dt
        if abs(stride - round(stride)) > 1e-6 or int(data["risk_labelling"]["horizon"]) < 1:
            raise ConfigError("Horizon must be positive with an integral simulation stride")
        if not data["risk_actor"]["blueprint_candidates"]:
            raise ConfigError("No primary actor blueprint candidates")
        if not isinstance(data["risk_labelling"]["horizon"], int):
            raise ConfigError("horizon must be an integer")
        for key in ("image_width", "image_height", "warmup_frames"):
            if not isinstance(data["recording"][key], int) or data["recording"][key] < 1:
                raise ConfigError(f"recording.{key} must be a positive integer")
        if data["recording"]["post_maneuver_seconds"] < data["risk_labelling"]["horizon"]*data["risk_labelling"]["horizon_step_seconds"]:
            raise ConfigError("post_maneuver_seconds must cover the full risk horizon")
        zone = data["placement"]["maneuver_zone_length_m"]
        if not 0 < zone < data["placement"]["minimum_route_length_m"]:
            raise ConfigError("Maneuver zone must fit within total route length")
        if scenario_id in {"INT-01", "INT-05"}:
            behavior = data["behavior"]
            if not 0 < behavior["merge_length_m"] < zone:
                raise ConfigError("Merge length must fit inside maneuver zone")
            if not 0 <= behavior["decision_lead_m"] <= 10:
                raise ConfigError("decision_lead_m must be within [0, 10]")
            if behavior["cf_safe_headway_seconds"] < data["acceptance"]["cf_headway_seconds"]:
                raise ConfigError("CF planning clearance cannot be below its acceptance threshold")
        if scenario_id != "INT-01":
            from ..scenarios.wave2_config import validate_wave2
            validate_wave2(data)
        elif data["risk_actor"].get("controller_gains"):
            raise ConfigError("INT-01 keeps its frozen legacy controller gains")
        if set(data["interventions"]) != {"R", "CF"}:
            raise ConfigError("Exactly R and CF interventions are required")
        modes = INTERVENTION_MODES[scenario_id]
        for branch, values in data["interventions"].items():
            if set(values) != {"mode"} or values["mode"] != modes[branch]:
                raise ConfigError("Interventions may only select actor behavior; ego/context overrides forbidden")
        rec = data["recording"]
        if not rec["save_rgb"] or rec["image_format"] not in {"jpeg", "jpg", "png"} or not 1 <= rec["jpeg_quality"] <= 100:
            raise ConfigError("Paired dataset requires valid RGB recording settings")
        ego = data["ego_vehicle"]
        if not 0 < ego["risk_slowdown_speed_kmh"] < ego["target_speed_kmh"] or not 0 < ego["risk_max_brake"] <= 1:
            raise ConfigError("Invalid ego slowdown/brake settings")
    except (KeyError, TypeError) as exc:
        raise ConfigError(f"Missing/invalid v2 configuration: {exc}") from exc


def load_pair_config(path: str | Path, overrides: dict | None = None) -> PairConfig:
    source = Path(path).resolve()
    raw = read_yaml(source)
    defaults = raw.pop("defaults", None)
    data = merge(read_yaml(source.parent / defaults) if defaults else {}, raw)
    data = merge(data, overrides or {})
    validate(data)
    root = next((p for p in source.parents if (p / "pyproject.toml").is_file()), PROJECT_ROOT)
    site = read_yaml(root / data["placement"]["site_file"])
    if site["map"] != data["carla"]["map"]:
        raise ConfigError("Site and CARLA map must match")
    data["site_selection"] = site["selection"]
    return PairConfig(data, source, root)
