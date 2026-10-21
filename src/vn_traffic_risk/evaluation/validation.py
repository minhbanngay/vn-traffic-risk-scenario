from __future__ import annotations

import json
import math
from pathlib import Path

from PIL import Image

from ..core.config import fingerprint, read_yaml
from ..core.models import decode_actor
from ..geometry.routes import RoadRoute
from .risk import observe
from .scenario_checks import check_wave2, completion_events
from ..recording.recorder import read_jsonl, write_json


def _json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _longest(mask, dt):
    best = current = 0
    for flag in mask:
        current = current+1 if flag else 0
        best = max(current, best)
    return best*dt


def evaluate_episode(path: str | Path) -> dict:
    path = Path(path)
    failures, metrics = [], {}
    try:
        summary = _json(path/"episode.json")
        cfg = read_yaml(path/"resolved_config.yaml")
        frames = read_jsonl(path/"frames.jsonl")
        if summary["status"] != "complete":
            failures.append("episode_not_complete")
        if not frames:
            raise ValueError("empty_episode")
        dt, acceptance = cfg["carla"]["fixed_delta_seconds"], cfg["acceptance"]
        layout = _json(path/"layout.json")
        road = RoadRoute(layout["ego_route"])
        collision_frames = {e["frame"] for e in summary["collision_events"]}
        for row in frames:
            ego, actor = decode_actor(row["ego"]), decode_actor(row["actors"][0])
            expected = observe(ego, actor, road.forward(road.station(ego.location)), cfg["risk_labelling"],
                               row["frame_id"] in collision_frames, any(f <= row["frame_id"] for f in collision_frames))
            for key, value in expected.items():
                actual = row["risk"].get(key)
                equal = abs(value-actual) < 1e-6 if type(value) is float and type(actual) in (float, int) else value == actual
                if not equal:
                    failures.append("metrics_or_labels_do_not_match_states")
                    break
            if failures and failures[-1] == "metrics_or_labels_do_not_match_states":
                break
        if [r["step_index"] for r in frames] != list(range(len(frames))):
            failures.append("non_contiguous_steps")
        ids = [r["frame_id"] for r in frames]
        if summary["frame_count"] != len(frames) or any(r["branch"] != summary["branch"] or r["pair_id"] != summary["pair_id"] for r in frames):
            failures.append("inconsistent_episode_identity")
        if ids != list(range(ids[0], ids[0]+len(ids))):
            failures.append("non_contiguous_sensor_frames")
        diagnostics = read_jsonl(path/"events.jsonl")
        if any(e["event"] == "rgb_received" and e.get("duplicate") and e.get("frame_id") in ids for e in diagnostics):
            failures.append("duplicate_rgb_callback")
        if any(abs((b["timestamp"]-a["timestamp"])-dt) > 1e-4 for a, b in zip(frames, frames[1:])):
            failures.append("invalid_timestamps")
        missing, invalid = [], []
        for row in frames:
            relative = row.get("rgb_file")
            image = (path/relative).resolve() if relative else None
            if image is None or not image.is_relative_to(path.resolve()) or not image.is_file():
                missing.append(row["step_index"])
                continue
            if image.stem != f'{row["frame_id"]:08d}' or row["sensor"]["image_frame_id"] != row["frame_id"]:
                invalid.append(row["step_index"])
            try:
                with Image.open(image) as rgb:
                    if rgb.size != (cfg["recording"]["image_width"], cfg["recording"]["image_height"]):
                        invalid.append(row["step_index"])
                    rgb.verify()
            except (OSError, ValueError):
                invalid.append(row["step_index"])
        if missing:
            failures.append("missing_rgb")
        if invalid:
            failures.append("invalid_rgb_alignment")
        metrics.update(frame_count=len(frames), missing_rgb=len(missing))
        if summary["collision_events"] or any(r["risk"]["collision_now"] or r["risk"]["collision_occurred"] for r in frames):
            failures.append("collision")
        events = summary["maneuver_events"]
        event_map = {e["event"]: e for e in events}
        sid = cfg["scenario"]["scenario_id"]
        started_event, completed_event = completion_events(sid)
        if not {"intervention", started_event, completed_event} <= event_map.keys():
            failures.append("maneuver_not_completed")
        elif not 0 <= event_map["intervention"]["step_index"] <= event_map[started_event]["step_index"] < event_map[completed_event]["step_index"] < len(frames):
            failures.append("invalid_maneuver_event_order")
        elif (frames[-1]["step_index"]-event_map[completed_event]["step_index"])*dt+1e-6 < cfg["recording"]["post_maneuver_seconds"]:
            failures.append("insufficient_post_maneuver_tail")
        risk_mask = [r["risk"]["corridor_overlap"] and r["risk"]["actor_ahead"] and r["risk"]["bumper_gap_m"] > 0
                     and 0 < r["risk"]["time_headway_seconds"] < acceptance["risk_headway_seconds"] for r in frames]
        metrics["critical_headway_duration_seconds"] = _longest(risk_mask, dt)
        if sid != "INT-01":
            scenario_failures, scenario_metrics = check_wave2(frames, event_map, cfg, summary["branch"], road)
            failures.extend(scenario_failures)
            metrics.update(scenario_metrics)
        elif summary["branch"] == "R":
            if metrics["critical_headway_duration_seconds"]+1e-6 < acceptance["risk_duration_seconds"]:
                failures.append("no_sustained_critical_headway")
            trigger = event_map.get("ego_response_triggered")
            speed_drop = 0.0
            if trigger:
                window = [r for r in frames if trigger["step_index"] <= r["step_index"] <= trigger["step_index"]+round(acceptance["ego_speed_drop_window_seconds"]/dt)]
                if window:
                    speed_drop = (trigger["speed_mps"]-min(r["ego"]["speed_mps"] for r in window))*3.6
                    if not any(r["controls"]["ego"]["brake"] > 0.01 for r in window):
                        failures.append("ego_did_not_brake")
            metrics["ego_speed_drop_kmh"] = speed_drop
            if not trigger or speed_drop+1e-6 < acceptance["ego_speed_drop_kmh"]:
                failures.append("insufficient_ego_response")
        else:
            merging = [r for r in frames if r["maneuver_state"] in {"merging", "completed"} and r["risk"]["corridor_overlap"]]
            if not merging or any(r["risk"]["actor_ahead"] or r["risk"]["time_headway_seconds"] < acceptance["cf_headway_seconds"] for r in merging):
                failures.append("unsafe_cf_merge")
            if any(r["risk"]["is_risk"] for r in frames) or "ego_response_triggered" in event_map:
                failures.append("cf_triggered_hazard")
        by_step = {r["step_index"]: r for r in frames}
        stride = round(cfg["risk_labelling"]["horizon_step_seconds"]/dt)
        for row in frames:
            future = [by_step.get(row["step_index"]+h*stride) for h in range(1, cfg["risk_labelling"]["horizon"]+1)]
            expected_valid = [r is not None for r in future]
            expected_values = [int(r["risk"]["is_risk"]) if r else 0 for r in future]
            if row.get("future_risk_valid") != expected_valid or row.get("future_risk_vector") != expected_values or bool(row["risk"]["reasons"]) != row["risk"]["is_risk"]:
                failures.append("invalid_risk_annotations")
                break
        if cfg["recording"].get("create_video") and not (path/"episode.mp4").is_file():
            failures.append("missing_video")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        failures.append(f"unreadable_episode: {exc}")
    return {"schema_version": 2, "passed": not failures, "failures": sorted(set(failures)), "metrics": metrics}


def evaluate_pair(path: str | Path, save=True) -> dict:
    path = Path(path)
    reports = {branch: evaluate_episode(path/branch) for branch in ("R", "CF")}
    failures = []
    prefix_metrics = {}
    try:
        manifest = _json(path/"pair.json")
        configs = {b: read_yaml(path/b/"resolved_config.yaml") for b in reports}
        layouts = [_json(path/b/"layout.json") for b in reports]
        for branch, cfg in configs.items():
            intervention = cfg.pop("intervention")
            if cfg.pop("branch") != branch or intervention != manifest["common_config"]["interventions"][branch]:
                failures.append("invalid_branch_intervention")
            if fingerprint(cfg) != manifest["config_fingerprint"]:
                failures.append("unmatched_common_configuration")
        if layouts[0] != layouts[1] or fingerprint(layouts[0]) != manifest["layout_fingerprint"]:
            failures.append("unmatched_frozen_layout")
        frames = {b: read_jsonl(path/b/"frames.jsonl") for b in reports}
        summaries = {b: _json(path/b/"episode.json") for b in reports}
        interventions = {b: next(e["step_index"] for e in summaries[b]["maneuver_events"] if e["event"] == "intervention") for b in reports}
        if interventions["R"] != interventions["CF"]:
            failures.append("unmatched_intervention_step")
        if manifest["common_config"]["scenario"]["scenario_id"] == "INT-08":
            braking_steps = {b: next(e["step_index"] for e in summaries[b]["maneuver_events"] if e["event"] == "braking_started") for b in reports}
            if braking_steps["CF"] >= braking_steps["R"]:
                failures.append("cf_did_not_brake_earlier")
        if "intervention_step_index" in layouts[0] and any(i != layouts[0]["intervention_step_index"] for i in interventions.values()):
            failures.append("frozen_intervention_not_followed")
        stop = min(interventions.values())
        if stop < 1:
            failures.append("empty_common_prefix")
        max_position = max_velocity = 0.0
        for index in range(stop):
            r, cf = frames["R"][index], frames["CF"][index]
            for first, second in ((r["ego"], cf["ego"]), (r["actors"][0], cf["actors"][0])):
                for field in ("location", "velocity"):
                    difference = math.sqrt(sum((first[field][axis]-second[field][axis])**2 for axis in "xyz"))
                    if field == "location":
                        max_position = max(max_position, difference)
                    else:
                        max_velocity = max(max_velocity, difference)
        acceptance = manifest["common_config"]["acceptance"]
        if max_position > acceptance["prefix_position_tolerance_m"] or max_velocity > acceptance["prefix_velocity_tolerance_mps"]:
            failures.append("common_prefix_diverged")
        prefix_metrics = {"position_error_m": max_position, "velocity_error_mps": max_velocity, "prefix_steps": stop}
    except (OSError, ValueError, KeyError, TypeError, StopIteration, IndexError) as exc:
        failures.append(f"incomplete_pair: {exc}")
    report = {"schema_version": 2, "passed": not failures and all(r["passed"] for r in reports.values()),
              "failures": failures, "branches": reports, "prefix": prefix_metrics}
    if save:
        write_json(path/"validation.json", report)
    return report
