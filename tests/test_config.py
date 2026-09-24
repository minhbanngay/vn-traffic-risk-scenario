from pathlib import Path

import pytest
import yaml

from vn_traffic_risk.config import ConfigError, load_config


CONFIG = Path(__file__).parents[1] / "configs" / "scenarios" / "motorcycle_cut_in.yaml"


def test_variant_override_is_resolved() -> None:
    config = load_config(CONFIG, "collision")
    assert config.variant == "collision"
    assert config.data["scenario"]["interaction_type"] == "collision"
    assert config.data["runtime"]["target_time_offset_seconds"] == 0.0
    assert config.data["ego_vehicle"]["reaction"] == "none"


def test_output_path_contains_scenario_episode_and_variant() -> None:
    config = load_config(CONFIG, "risk")
    path = config.output_directory.as_posix()
    assert path.endswith("outputs/INT_MOTO_001/INT_MOTO_001_V008/risk")


def test_recording_uses_compressed_jpeg() -> None:
    config = load_config(CONFIG, "risk")
    assert config.data["recording"]["image_format"] == "jpeg"
    assert config.data["recording"]["jpeg_quality"] == 85


def test_risk_variant_uses_requested_cut_in_geometry() -> None:
    config = load_config(CONFIG, "risk")
    assert config.data["placement"]["lane_change_side"] == "left"
    assert config.data["placement"]["actor_start_behind_ego_m"] == 8.0
    assert config.data["ego_vehicle"]["initial_speed_kmh"] == 25.0
    assert config.data["risk_actor"]["initial_speed_kmh"] == 38.0
    assert config.data["runtime"]["target_time_offset_seconds"] == -1.25
    assert config.data["ego_vehicle"]["risk_slowdown_speed_kmh"] == 12.5
    assert config.data["ego_vehicle"]["risk_max_brake"] == 0.15


def test_invalid_jpeg_quality_is_rejected(tmp_path: Path) -> None:
    data = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    data["recording"]["jpeg_quality"] = 101
    invalid_config = tmp_path / "invalid.yaml"
    invalid_config.write_text(yaml.safe_dump(data), encoding="utf-8")

    with pytest.raises(ConfigError, match="jpeg_quality"):
        load_config(invalid_config)
