"""Additional offline checks; never edits frames, labels or acceptance thresholds."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess

from vn_traffic_risk.core.config import read_yaml
from vn_traffic_risk.core.batch import evaluate_repeats
from vn_traffic_risk.core.models import decode_actor
from vn_traffic_risk.evaluation.validation import evaluate_pair
from vn_traffic_risk.evaluation.scenario_checks import completion_events
from vn_traffic_risk.geometry.routes import RoadRoute
from vn_traffic_risk.recording.recorder import read_jsonl, write_json


def decoded_video_frames(path):
    import imageio_ffmpeg
    result = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),"-nostdin","-v","error","-xerror",
                             "-threads","1","-i",str(path),"-map","0:v:0","-progress","pipe:1",
                             "-nostats","-f","null","-"],capture_output=True,text=True,timeout=90,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0)
    if result.returncode:
        raise RuntimeError(f"Video decode failed: {result.stderr[:1000]}")
    counts = [int(line.partition("=")[2].strip()) for line in result.stdout.splitlines() if line.startswith("frame=")]
    if not counts:
        raise RuntimeError("Video decoder reported no frames")
    return counts[-1]


def route_tail_audit(rows,layout,completed_step,actor_lateral=0.0):
    road = RoadRoute(layout["ego_route"])
    report = {}
    for role in ("ego","primary_risk_actor"):
        states = [decode_actor(r["ego"] if role=="ego" else r["actors"][0])
                  for r in rows if r["step_index"] >= completed_step]
        stations = [road.station(s.location) for s in states]
        speeds = [sum(v*f for v,f in zip((s.velocity.x,s.velocity.y),road.forward(station)))
                  for s,station in zip(states,stations)]
        monotonic = bool(stations) and all(b+1e-6>=a for a,b in zip(stations,stations[1:]))
        report[role] = {"station_monotonic":monotonic,"min_forward_speed_mps":min(speeds,default=0),
                        "max_lateral_error_m":max((abs(road.lateral(s.location)-(actor_lateral if role=="primary_risk_actor" else 0)) for s in states),default=None),
                        "distance_after_merge_m":stations[-1]-stations[0] if stations else 0}
    report["passed"] = all(r["station_monotonic"] and r["min_forward_speed_mps"] > 0 for r in report.values())
    return report


def audit_attempt(path):
    path = Path(path)
    result = {"path":str(path),"validation":evaluate_pair(path,save=False),"branches":{},"gpu":{}}
    cfg = read_yaml(path/"R/resolved_config.yaml")
    sid = cfg["scenario"]["scenario_id"]
    _, completed_event = completion_events(sid)
    for branch in ("R","CF"):
        try:
            rows = read_jsonl(path/branch/"frames.jsonl")
            summary = json.loads((path/branch/"episode.json").read_text(encoding="utf-8"))
            layout = json.loads((path/branch/"layout.json").read_text(encoding="utf-8"))
            completed = next(e["step_index"] for e in summary["maneuver_events"] if e["event"]==completed_event)
            count = decoded_video_frames(path/branch/"episode.mp4")
            tail = route_tail_audit(rows,layout,completed,layout.get("actor_lateral_m",0) if sid=="INT-03" else 0)
            result["branches"][branch] = {"decoded_video_frames":count,"recorded_frames":len(rows),
                                          "route_tail":tail,"passed":count==len(rows) and tail["passed"]}
        except (OSError,ValueError,KeyError,StopIteration,RuntimeError,subprocess.SubprocessError) as exc:
            result["branches"][branch] = {"passed":False,"error":str(exc)}
    if cfg["carla"].get("managed_server") and cfg["carla"].get("health_monitor",{}).get("enabled"):
        for stage in ("planner","R","CF"):
            try:
                events = read_jsonl(path/f"server_{stage}.telemetry.jsonl")
                gpus = [gpu for event in events if event["event"]=="gpu_sample" for gpu in event["gpus"]]
                stops = sum(event["event"]=="health_guard_stop" for event in events)
                result["gpu"][stage] = {"sample_count":len(gpus),"guard_stops":stops,
                    "max_temperature_c":max((g["temperature.gpu"] for g in gpus),default=None),
                    "max_vram_mib":max((g["memory.used"] for g in gpus),default=None),"passed":bool(gpus) and not stops}
            except (OSError,ValueError,KeyError) as exc:
                result["gpu"][stage] = {"passed":False,"error":str(exc)}
    result["passed"] = result["validation"]["passed"] and all(r["passed"] for r in result["branches"].values()) and all(r["passed"] for r in result["gpu"].values())
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batch",help="A batch directory or a single R-CF pair attempt")
    parser.add_argument("--output",help="New audit JSON; existing files are never overwritten")
    args = parser.parse_args()
    batch_path = Path(args.batch).resolve()
    if (batch_path/"pair.json").is_file():
        report = audit_attempt(batch_path)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        output = Path(args.output) if args.output else batch_path/f"audit-{stamp}.json"
        if output.exists():
            raise FileExistsError(output)
        write_json(output,report)
        print(json.dumps({"output":str(output),"passed":report["passed"],"audited_attempts":1}))
        return 0 if report["passed"] else 1
    manifest = json.loads((batch_path/"manifest.json").read_text(encoding="utf-8"))
    paths = [s["selected"] for s in manifest["samples"] if s["selected"]]+manifest["baseline_repeats"]
    reports = [audit_attempt(p) for p in paths]
    accepted = sum(bool(s["selected"]) for s in manifest["samples"])
    repeatability = {"passed":False,"reason":"pending_baseline"}
    if manifest.get("baseline_selected"):
        baseline = Path(manifest["baseline_selected"])
        cfg = read_yaml(baseline/"R/resolved_config.yaml")
        repeatability = evaluate_repeats([str(baseline),*manifest["baseline_repeats"]],
                                       cfg["acceptance"]["repeat_event_tolerance_seconds"])
    report = {"schema_version":2,"batch_id":manifest["batch_id"],"accepted_pairs":accepted,
              "planned_pairs":len(manifest["samples"]),"attempts":reports,"repeatability":repeatability,
              "passed":manifest["status"]=="passed" and accepted==len(manifest["samples"]) and repeatability["passed"]
                       and bool(reports) and all(r["passed"] for r in reports)}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = Path(args.output) if args.output else batch_path/f"audit-{stamp}.json"
    if output.exists():
        raise FileExistsError(output)
    write_json(output,report)
    print(json.dumps({"output":str(output),"passed":report["passed"],"audited_attempts":len(reports)}))
    return 0 if report["passed"] else 1


if __name__=="__main__":
    raise SystemExit(main())
