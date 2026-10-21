"""Configuration contracts, independent of CARLA and live map availability."""
import math

from ..config import ConfigError


def validate_wave2(data):
    sid = data["scenario"]["scenario_id"]
    behavior, acceptance = data["behavior"], data["acceptance"]
    gains = data["risk_actor"].get("controller_gains", {})
    if not isinstance(gains, dict) or set(gains)-{"speed_kp", "speed_ki", "heading_kp", "heading_kd"}:
        raise ConfigError("Unsupported actor controller gains")
    if any(not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) or v < 0 for v in gains.values()):
        raise ConfigError("Actor controller gains must be finite and nonnegative")
    if gains.get("speed_kp", 0.55) <= 0 or gains.get("heading_kp", 1.35) <= 0:
        raise ConfigError("Proportional gains must be positive")
    for section in (behavior, acceptance):
        if any(not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) or v < 0 for v in section.values()):
            raise ConfigError("Wave-2 behavior and acceptance values must be finite nonnegative numbers")
    if not 0 < behavior["completion_lateral_tolerance_m"] <= 0.5:
        raise ConfigError("Invalid lane completion tolerance")
    if sid in {"INT-03", "INT-08"}:
        if not 0 < behavior["decision_after_seconds"] < data["recording"]["max_episode_seconds"]:
            raise ConfigError("Decision must occur inside the episode after a common approach")
    if sid == "INT-03":
        if abs(data["risk_actor"]["initial_speed_kmh"]-data["ego_vehicle"]["initial_speed_kmh"]) > 0.1:
            raise ConfigError("INT-03 requires initially parallel actors with equal speeds")
        if not 0 < behavior["transition_length_m"] < data["placement"]["maneuver_zone_length_m"]/2:
            raise ConfigError("Squeeze and separation must fit inside maneuver zone")
        if not 0 < behavior["risk_lateral_clearance_m"] < acceptance["risk_lateral_clearance_m"] < acceptance["cf_lateral_clearance_m"]:
            raise ConfigError("INT-03 requires distinct positive risky/safe lateral clearances")
        if data["risk_labelling"]["lateral_clearance_m"] != acceptance["risk_lateral_clearance_m"]:
            raise ConfigError("Lateral detector and acceptance thresholds must agree")
        if behavior["hold_seconds"] <= 0 or behavior["cf_observation_seconds"] <= 0:
            raise ConfigError("Squeeze hold and CF observation must be positive")
    elif sid == "INT-05":
        if data["risk_actor"]["initial_speed_kmh"] <= data["ego_vehicle"]["target_speed_kmh"]:
            raise ConfigError("Overtaking actor must be faster than ego")
        if not data["ego_vehicle"]["target_speed_kmh"] < behavior["merge_speed_kmh"] <= data["risk_actor"]["initial_speed_kmh"]:
            raise ConfigError("Reentry speed must exceed ego speed and not exceed actor cruise")
        if not 0 < behavior["completion_heading_tolerance_degrees"] <= 5:
            raise ConfigError("Reentry must stabilize heading before completion")
    elif sid == "INT-08":
        rear = data["placement"]["site_search_rear_clearance_m"]
        if not math.isfinite(rear) or rear <= 0:
            raise ConfigError("Site search clearance must be positive")
        ahead = data["placement"]["actor_start_ahead_ego_m"]
        if not math.isfinite(ahead) or not 0 < ahead < data["placement"]["maneuver_zone_length_m"]:
            raise ConfigError("Lead actor must start ahead inside the protected zone")
        if data["risk_actor"]["initial_speed_kmh"] != data["ego_vehicle"]["initial_speed_kmh"]:
            raise ConfigError("Lead-braking approach must start at equal speeds")
        if not 0 < behavior["cf_deceleration_mps2"] < behavior["risk_deceleration_mps2"]:
            raise ConfigError("CF must decelerate more gradually than R")
        if not 0 < behavior["risk_target_speed_kmh"] < behavior["cf_target_speed_kmh"] < data["risk_actor"]["initial_speed_kmh"]:
            raise ConfigError("Invalid braking speed targets")
        if not 0 < behavior["cf_max_brake"] < behavior["risk_max_brake"] <= 1:
            raise ConfigError("Invalid actor braking limits")
        if behavior["risk_brake_delay_seconds"] <= 0 or behavior["recovery_acceleration_mps2"] <= 0:
            raise ConfigError("R delay and speed recovery must be positive")
        if not 0 < behavior["speed_tolerance_mps"] <= 0.5:
            raise ConfigError("Invalid speed completion tolerance")
        if data["risk_labelling"]["closing_ttc_seconds"] != acceptance["risk_ttc_seconds"]:
            raise ConfigError("Closing detector and acceptance thresholds must agree")
