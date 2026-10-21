from pathlib import Path

import pytest

from vn_traffic_risk.config import ConfigError
from vn_traffic_risk.core.batch import expand_batch, nested_overrides
from vn_traffic_risk.core.config import PROJECT_ROOT, load_pair_config, read_yaml


CONFIG = PROJECT_ROOT/"configs/scenarios/group_a/INT-01.yaml"


def test_pair_context_is_equal_and_mutation_isolated():
    config = load_pair_config(CONFIG)
    r, cf = config.branch("R"), config.branch("CF")
    assert r["ego_vehicle"] == cf["ego_vehicle"]
    assert r["carla"] == cf["carla"]
    r["ego_vehicle"]["target_speed_kmh"] = 100
    assert config.data["ego_vehicle"]["target_speed_kmh"] == 25
    assert config.pair_id == load_pair_config(CONFIG).pair_id


@pytest.mark.parametrize("override", [
    {"interventions": {"R": {"ego_vehicle": {"target_speed_kmh": 10}}}},
    {"recording": {"camera_tick_seconds": 0.1}},
    {"placement": {"actor_start_behind_ego_m": -1}},
    {"risk_actor": {"initial_speed_kmh": float("nan")}},
    {"carla": {"synchronous_mode": False}},
    {"carla": {"server_max_fps":0}},
    {"carla": {"health_monitor":{"max_gpu_temperature_c":float("nan")}}},
    {"carla": {"health_monitor":{"max_probe_errors":0}}},
])
def test_invalid_or_unmatched_pair_config_rejected(override):
    with pytest.raises(ConfigError):
        load_pair_config(CONFIG, override)


def test_catalog_and_ten_pair_matrix():
    catalog = read_yaml(PROJECT_ROOT/"configs/catalog.yaml")["scenarios"]
    assert [s["id"] for s in catalog] == [f"INT-{i:02d}" for i in range(1, 21)]
    assert sum(s["status"] == "planned" for s in catalog) == 16
    batch, source, samples = expand_batch(PROJECT_ROOT/"configs/batches/int_01_pilot.yaml")
    assert len(samples) == 10 and batch["baseline"] in samples
    assert len({load_pair_config(source, nested_overrides(s)).pair_id for s in samples}) == 10
