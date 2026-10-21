"""Scenario-specific acceptance, separate from recording/pair invariants.

All metrics come from recorded states (labels are independently recomputed by
validation.py). No branch is accepted merely because of its configured mode.
"""
from __future__ import annotations

from ..core.models import decode_actor


def completion_events(scenario_id):
    return ("merge_started", "merge_completed") if scenario_id in {"INT-01", "INT-05"} else ("maneuver_started", "maneuver_completed")


def longest(mask, dt):
    best = current = 0
    for flag in mask:
        current = current+1 if flag else 0
        best = max(best, current)
    return best*dt


def check_wave2(frames, event_map, cfg, branch, road):
    sid, dt = cfg["scenario"]["scenario_id"], cfg["carla"]["fixed_delta_seconds"]
    acceptance = cfg["acceptance"]
    failures, metrics = [], {}
    decision = event_map.get("intervention", {}).get("step_index", len(frames))
    active = [r for r in frames if r["step_index"] >= decision]
    if any(r["risk"]["is_risk"] for r in frames if r["step_index"] < decision):
        failures.append("hazard_before_intervention")
    if sid == "INT-03":
        risk_mask = [r["risk"]["longitudinal_overlap"] and 0 < r["risk"]["lateral_clearance_m"] < acceptance["risk_lateral_clearance_m"] for r in active]
        metrics["critical_lateral_duration_seconds"] = longest(risk_mask, dt)
        metrics["minimum_lateral_clearance_m"] = min(r["risk"]["lateral_clearance_m"] for r in frames)
        if not frames[0]["risk"]["longitudinal_overlap"]:
            failures.append("motorcycle_not_initially_parallel")
        if branch == "R":
            if metrics["critical_lateral_duration_seconds"]+1e-6 < acceptance["risk_duration_seconds"]:
                failures.append("no_sustained_lateral_squeeze")
            if any(r["risk"]["longitudinal_overlap"] and r["risk"]["lateral_clearance_m"] <= 0 for r in frames):
                failures.append("body_clearance_violation")
            if not {"squeeze_reached", "separation_started"} <= event_map.keys():
                failures.append("squeeze_not_executed")
        elif any(r["risk"]["lateral_clearance_m"] < acceptance["cf_lateral_clearance_m"] for r in frames):
            failures.append("unsafe_cf_lateral_clearance")
    elif sid == "INT-05":
        risk_mask = [r["risk"]["corridor_overlap"] and r["risk"]["actor_ahead"] and r["risk"]["bumper_gap_m"] > 0
                     and 0 < r["risk"]["time_headway_seconds"] < acceptance["risk_headway_seconds"] for r in active]
        metrics["critical_headway_duration_seconds"] = longest(risk_mask, dt)
        if frames[0]["risk"]["actor_ahead"] or not frames[-1]["risk"]["actor_ahead"]:
            failures.append("overtake_not_observed")
        if branch == "R":
            if metrics["critical_headway_duration_seconds"]+1e-6 < acceptance["risk_duration_seconds"]:
                failures.append("no_sustained_critical_headway")
        else:
            merging = [r for r in active if r["maneuver_state"] in {"merging", "settling", "completed"} and r["risk"]["corridor_overlap"]]
            metrics["minimum_cf_merge_headway_seconds"] = min((r["risk"]["time_headway_seconds"] for r in merging), default=None)
            if not merging or any(not r["risk"]["actor_ahead"] or r["risk"]["time_headway_seconds"] < acceptance["cf_headway_seconds"] for r in merging):
                failures.append("unsafe_cf_overtaking_reentry")
    elif sid == "INT-08":
        risk_mask = [r["risk"]["corridor_overlap"] and r["risk"]["actor_ahead"] and r["risk"]["ttc_seconds"] is not None
                     and 0 < r["risk"]["ttc_seconds"] < acceptance["risk_ttc_seconds"] for r in active]
        metrics["critical_ttc_duration_seconds"] = longest(risk_mask, dt)
        braking = [r for r in active if r["maneuver_state"] == "braking"]
        decelerations = []
        for row in braking:
            state = decode_actor(row["actors"][0])
            fx, fy = road.forward(road.station(state.location))
            decelerations.append(max(0, -state.acceleration.x*fx-state.acceleration.y*fy))
        metrics["actor_peak_deceleration_mps2"] = max(decelerations, default=0)
        start_step = event_map.get("braking_started", {}).get("step_index", 0)
        reference_speed = frames[max(0, min(len(frames)-1, start_step-1))]["actors"][0]["speed_mps"]
        metrics["actor_speed_drop_kmh"] = (reference_speed-min((r["actors"][0]["speed_mps"] for r in braking), default=reference_speed))*3.6
        if not {"braking_started", "braking_target_reached", "recovery_started"} <= event_map.keys() or not braking:
            failures.append("braking_not_executed")
        else:
            start = event_map["braking_started"]["step_index"]
            reached = event_map["braking_target_reached"]["step_index"]
            recovery = event_map["recovery_started"]["step_index"]
            completed = event_map.get("maneuver_completed", {}).get("step_index", -1)
            if not 0 < decision <= start < reached <= recovery < completed < len(frames):
                failures.append("invalid_braking_event_order")
            else:
                floor = cfg["behavior"]["risk_target_speed_kmh" if branch == "R" else "cf_target_speed_kmh"]/3.6
                tolerance = cfg["behavior"]["speed_tolerance_mps"]
                # Events describe the pre-control state, i.e. the preceding
                # recorded frame, not the post-tick frame bearing the event.
                if frames[reached-1]["actors"][0]["speed_mps"] > floor+tolerance:
                    failures.append("braking_target_not_observed")
                if frames[completed-1]["actors"][0]["speed_mps"] < cfg["risk_actor"]["initial_speed_kmh"]/3.6-tolerance:
                    failures.append("cruise_recovery_not_observed")
        if any(not r["risk"]["actor_ahead"] or not r["risk"]["corridor_overlap"] for r in frames):
            failures.append("lead_motorcycle_left_corridor")
        if branch == "R":
            if metrics["critical_ttc_duration_seconds"]+1e-6 < acceptance["risk_duration_seconds"]:
                failures.append("no_sustained_closing_conflict")
            if metrics["actor_peak_deceleration_mps2"]+1e-6 < acceptance["risk_min_deceleration_mps2"]:
                failures.append("risk_braking_not_abrupt")
        else:
            if metrics["actor_peak_deceleration_mps2"] > acceptance["cf_max_deceleration_mps2"]+1e-6:
                failures.append("cf_braking_not_gradual")
            if metrics["actor_speed_drop_kmh"]+1e-6 < acceptance["cf_min_speed_drop_kmh"]:
                failures.append("cf_did_not_decelerate")
            if any(r["risk"]["time_headway_seconds"] < acceptance["cf_headway_seconds"] for r in frames):
                failures.append("unsafe_cf_following_headway")
    else:
        return ["unsupported_acceptance_profile"], {}
    if branch == "R":
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
    elif any(r["risk"]["is_risk"] for r in frames) or "ego_response_triggered" in event_map:
        failures.append("cf_triggered_hazard")
    _, completed_event = completion_events(sid)
    completion = event_map.get(completed_event)
    if completion:
        tail = [r for r in frames if r["step_index"] >= completion["step_index"]]
        for role in ("ego", "actor"):
            states = [decode_actor(r["ego"] if role == "ego" else r["actors"][0]) for r in tail]
            stations = [road.station(s.location) for s in states]
            desired_lateral = cfg["behavior"].get("completed_lateral_m", 0.0)
            if sid == "INT-03" and role == "actor":
                # Initial lane center is measured from the actual frozen spawn.
                desired_lateral = road.lateral(decode_actor(frames[0]["actors"][0]).location)
            if any(b < a-0.05 for a, b in zip(stations, stations[1:])) or (len(stations) > 1 and stations[-1] <= stations[0]):
                failures.append("non_forward_recording_tail")
            if any(abs(road.lateral(s.location)-desired_lateral) > cfg["behavior"]["completion_lateral_tolerance_m"] for s in states):
                failures.append("off_route_after_completion")
    return failures, metrics
