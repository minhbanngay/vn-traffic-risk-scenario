"""Synthetic episode contract tests; these are not collected CARLA outputs."""
import json

from PIL import Image
import pytest

from vn_traffic_risk.core.config import PROJECT_ROOT, load_pair_config
from vn_traffic_risk.evaluation.risk import observe
from vn_traffic_risk.evaluation.validation import evaluate_episode
from vn_traffic_risk.models import ActorState, Vec3
from vn_traffic_risk.recording.recorder import EpisodeRecorder, read_jsonl


def state(role, x, y, speed, acceleration=0):
    return ActorState(1 if role == "ego" else 2, role, "vehicle.fixture", Vec3(x, y), Vec3(0, 0),
                      Vec3(speed, 0), Vec3(acceleration, 0), speed, 1, 1,
                      Vec3(2.4, 0.95, 1) if role == "ego" else Vec3(1, 0.4, 1))


@pytest.fixture(params=[("INT-03", "R"), ("INT-03", "CF"), ("INT-05", "R"), ("INT-05", "CF"),
                       ("INT-08", "R"), ("INT-08", "CF")])
def synthetic_episode(tmp_path, request):
    sid, branch = request.param
    group = "group_b" if sid == "INT-08" else "group_a"
    cfg = load_pair_config(PROJECT_ROOT/f"configs/scenarios/{group}/{sid}.yaml",
                           {"recording": {"image_width": 8, "image_height": 4, "create_video": False}})
    layout = {"ego_route": [{"x": 0, "y": 0, "z": 0}, {"x": 200, "y": 0, "z": 0}]}
    path = tmp_path/sid/branch
    identity = {"schema_version": 2, "scenario_id": sid, "branch": branch, "pair_id": "fixture", "attempt_id": "fixture"}
    recorder = EpisodeRecorder(path, cfg.branch(branch), layout, identity)
    for index in range(130):
        active = 5 <= index < 20
        speed = 5 if branch == "R" and index >= 15 else 25/3.6
        ego = state("ego", index*0.35, 0, speed)
        if sid == "INT-03":
            x, y, v, a = ego.location.x-1, -1.7 if branch == "R" and active else -3.5, 25/3.6, 0
            maneuver = "completed" if index >= 20 else "holding_clearance" if active else "approaching"
        elif sid == "INT-05":
            x = ego.location.x+ (6 if branch == "R" else 25) if index >= 5 else ego.location.x-8
            y, v, a = (0 if index >= 5 else -3.5), 12.5, 0
            maneuver = "completed" if index >= 20 else "merging" if active else "approaching"
        else:
            braking = (10 if branch == "R" else 5) <= index < 19
            x, y = ego.location.x+(12 if branch == "R" and braking else 24), 0
            v = (8/3.6 if branch == "R" else 18/3.6) if braking else 25/3.6
            a = (-3 if branch == "R" else -0.7) if braking else 0
            maneuver = "completed" if index >= 20 else "braking" if braking else "anticipating" if index >= 5 else "approaching"
        actor = state("primary_risk_actor", x, y, v, a)
        frame = index+1000
        relative = f"rgb/{frame:08d}.jpg"
        Image.new("RGB", (8, 4)).save(path/relative)
        recorder.append({**identity, "step_index": index, "frame_id": frame, "timestamp": index*0.05,
                         "relative_time_seconds": index*0.05, "rgb_file": relative, "ego": ego.as_dict(),
                         "actors": [actor.as_dict()], "risk": observe(ego, actor, (1, 0), cfg.data["risk_labelling"]),
                         "maneuver_state": maneuver, "sensor": {"image_frame_id": frame},
                         "controls": {"ego": {"brake": 0.15 if branch == "R" and index >= 15 else 0}}})
    recorder.event({"event": "intervention", "step_index": 5})
    for event, step in (("merge_started", 5), ("merge_completed", 20)) if sid == "INT-05" else (("maneuver_started", 10 if sid == "INT-08" and branch == "R" else 5), ("maneuver_completed", 20)):
        recorder.event({"event": event, "step_index": step})
    if sid == "INT-03" and branch == "R":
        for event, step in (("squeeze_reached", 10), ("separation_started", 18)):
            recorder.event({"event": event, "step_index": step})
    if sid == "INT-08":
        for event, step in (("braking_started", 10 if branch == "R" else 5), ("braking_target_reached", 18), ("recovery_started", 19)):
            recorder.event({"event": event, "step_index": step})
    if branch == "R":
        recorder.event({"event": "ego_response_triggered", "step_index": 10, "speed_mps": 25/3.6})
    recorder.finalize([])
    recorder.close()
    return path


def test_scenario_specific_episode_contract(synthetic_episode):
    result = evaluate_episode(synthetic_episode)
    assert result["passed"], result


def test_missing_image_is_rejected_for_every_new_profile(synthetic_episode):
    (synthetic_episode/"rgb/00001030.jpg").unlink()
    assert "missing_rgb" in evaluate_episode(synthetic_episode)["failures"]


def test_new_metrics_cannot_be_forged(synthetic_episode):
    rows = read_jsonl(synthetic_episode/"frames.jsonl")
    rows[10]["risk"]["bumper_gap_m"] = 900
    (synthetic_episode/"frames.jsonl").write_text("".join(json.dumps(r)+"\n" for r in rows), encoding="utf-8")
    assert "metrics_or_labels_do_not_match_states" in evaluate_episode(synthetic_episode)["failures"]
