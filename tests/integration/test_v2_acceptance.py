import json

import yaml

from vn_traffic_risk.evaluation.validation import evaluate_pair
from vn_traffic_risk.recording.recorder import read_jsonl


def rewrite(path, rows):
    path.write_text("".join(json.dumps(row)+"\n" for row in rows),encoding="utf-8")


def test_valid_pair_passes_with_different_absolute_carla_frame_ids(recorded_pair):
    report = evaluate_pair(recorded_pair)
    assert report["passed"], report
    assert report["prefix"]["position_error_m"] == 0


def test_missing_rgb_cannot_be_accepted(recorded_pair):
    (recorded_pair/"CF/rgb/00003001.jpg").unlink()
    report = evaluate_pair(recorded_pair)
    assert not report["passed"]
    assert "missing_rgb" in report["branches"]["CF"]["failures"]


def test_metrics_are_recomputed_not_trusted(recorded_pair):
    path = recorded_pair/"R/frames.jsonl"
    frames = read_jsonl(path)
    frames[6]["risk"]["bumper_gap_m"] = 99
    rewrite(path,frames)
    report = evaluate_pair(recorded_pair)
    assert "metrics_or_labels_do_not_match_states" in report["branches"]["R"]["failures"]


def test_unknown_future_cannot_be_marked_observed(recorded_pair):
    path = recorded_pair/"R/frames.jsonl"
    frames = read_jsonl(path)
    frames[-1]["future_risk_valid"][-1] = True
    rewrite(path,frames)
    report = evaluate_pair(recorded_pair)
    assert "invalid_risk_annotations" in report["branches"]["R"]["failures"]


def test_counterfactual_cannot_change_ego_configuration(recorded_pair):
    path = recorded_pair/"CF/resolved_config.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["ego_vehicle"]["target_speed_kmh"] = 10
    path.write_text(yaml.safe_dump(data),encoding="utf-8")
    report = evaluate_pair(recorded_pair)
    assert "unmatched_common_configuration" in report["failures"]


def test_prefix_drift_is_rejected(recorded_pair):
    path = recorded_pair/"CF/frames.jsonl"
    frames = read_jsonl(path)
    frames[1]["ego"]["location"]["x"] += 0.2
    rewrite(path,frames)
    assert "common_prefix_diverged" in evaluate_pair(recorded_pair)["failures"]
