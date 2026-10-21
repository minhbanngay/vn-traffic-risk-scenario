from __future__ import annotations

from itertools import product
import json
from pathlib import Path

from ..evaluation.validation import evaluate_pair
from ..recording.recorder import write_json
from .config import fingerprint, implementation_fingerprint, load_pair_config, read_yaml, runtime_environment
from .pairing import run_pair
from .registry import BATCH_FIELDS, CALIBRATION_FIELDS


def nested_overrides(values: dict) -> dict:
    result = {}
    for dotted, value in values.items():
        node = result
        parts = dotted.split(".")
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value
    return result


def expand_batch(path: str | Path):
    path = Path(path).resolve()
    data = read_yaml(path)
    keys = list(data["matrix"])
    scenario_path = path.parent/data["scenario_config"]
    sid = load_pair_config(scenario_path).data["scenario"]["scenario_id"]
    allowed = BATCH_FIELDS[sid]
    if set(keys) != allowed or any(not data["matrix"][key] for key in keys):
        raise ValueError(f"{sid} matrix requires exactly {sorted(allowed)}")
    samples = [dict(zip(keys, combination)) for combination in product(*(data["matrix"][key] for key in keys))]
    if len({fingerprint(s) for s in samples}) != len(samples) or data["baseline"] not in samples:
        raise ValueError("Batch matrix must be unique and contain its baseline")
    calibration_key = CALIBRATION_FIELDS[sid]
    if data["baseline_runs"] != 3 or set(data["calibration"]) != {calibration_key} or not data["calibration"][calibration_key]:
        raise ValueError("Pilot requires three baseline runs and a finite calibration list")
    for sample in samples:
        for value in data["calibration"][calibration_key]:
            load_pair_config(scenario_path, nested_overrides({**sample, f"behavior.{calibration_key}": value}))
    return data, scenario_path, samples


def evaluate_repeats(attempts, tolerance):
    if len(attempts) != 3:
        return {"passed": False, "reason": "three_passed_baseline_attempts_required"}
    events = []
    for path in attempts:
        report = evaluate_pair(path)
        if not report["passed"]:
            return {"passed": False, "reason": "baseline_attempt_rejected"}
        manifest = json.loads((Path(path)/"pair.json").read_text(encoding="utf-8"))
        layout = json.loads((Path(path)/"R/layout.json").read_text(encoding="utf-8"))
        static_layout = {k:v for k,v in layout.items() if k not in {"intervention_step_index","intervention_reference"}}
        values = {"config": manifest["config_fingerprint"], "layout": fingerprint(static_layout),
                  "runtime":manifest.get("runtime_fingerprint","legacy"),
                  "implementation":manifest.get("implementation_fingerprint","legacy")}
        for branch in ("R", "CF"):
            episode = json.loads((Path(path)/branch/"episode.json").read_text(encoding="utf-8"))
            dt = manifest["common_config"]["carla"]["fixed_delta_seconds"]
            for event in episode["maneuver_events"]:
                values[f'{branch}:{event["event"]}'] = event["step_index"]*dt
        events.append(values)
    if any(e.keys() != events[0].keys() for e in events):
        return {"passed": False, "reason": "repeat_event_sets_differ"}
    identity_keys = {"config","layout","runtime","implementation"}
    differences = {key: max(e[key] for e in events)-min(e[key] for e in events) for key in events[0] if key not in identity_keys}
    identity_equal = all(all(e[key]==events[0][key] for key in identity_keys) for e in events)
    return {"passed": identity_equal and all(d <= tolerance+1e-6 for d in differences.values()), "event_spread_seconds": differences}


def run_batch(path: str | Path, max_new_attempts=None):
    if max_new_attempts is not None and (not isinstance(max_new_attempts,int) or max_new_attempts < 1):
        raise ValueError("max_new_attempts must be a positive integer")
    batch, scenario_path, samples = expand_batch(path)
    base = load_pair_config(scenario_path)
    calibration_key = CALIBRATION_FIELDS[base.data["scenario"]["scenario_id"]]
    directory = base.output_root/"batches"/batch["batch_id"]
    directory.mkdir(parents=True, exist_ok=True)
    implementation = implementation_fingerprint()
    environment = runtime_environment()
    signature = fingerprint({"batch": batch, "scenario": base.data, "implementation": implementation,"runtime":environment})
    manifest_path = directory/"manifest.json"
    lock = directory/"batch.lock"
    try:
        handle = lock.open("x")
    except FileExistsError as exc:
        raise RuntimeError(f"Batch lock exists: {lock}; ensure no runner is active before removing a stale lock") from exc
    try:
        handle.close()
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest["fingerprint"] != signature:
                raise ValueError("Batch config changed; choose a new batch_id to preserve previous evidence")
        else:
            manifest = {"schema_version": 2, "batch_id": batch["batch_id"], "fingerprint": signature,
                        "implementation_fingerprint": implementation, "status": "running",
                        "runtime_environment":environment,
                        "samples": [{"parameters": s, "attempts": [], "selected": None} for s in samples], "baseline_repeats": []}
        manifest["status"] = "running"
        manifest.pop("error",None)
        write_json(manifest_path, manifest)
        new_attempts = 0
        for slot in manifest["samples"]:
            if implementation_fingerprint() != implementation:
                raise RuntimeError("Implementation changed during batch; use a new batch ID after completing code changes")
            if slot["selected"] and evaluate_pair(slot["selected"])["passed"]:
                continue
            slot["selected"] = None
            for lead in batch["calibration"][calibration_key]:
                previous = [a for a in slot["attempts"] if a[calibration_key] == lead]
                if previous:
                    passed = next((a["path"] for a in previous if evaluate_pair(a["path"])["passed"]), None)
                    if passed:
                        slot["selected"] = passed
                        break
                    # Retry failed/interrupted workers; keep completed rejected evidence.
                    if all(json.loads((Path(a["path"])/"pair.json").read_text(encoding="utf-8"))["status"] == "rejected" for a in previous):
                        continue
                values = {**slot["parameters"], f"behavior.{calibration_key}": lead}
                config = load_pair_config(scenario_path, nested_overrides(values))
                if batch.get("managed_server"):
                    config = load_pair_config(scenario_path, {**nested_overrides(values), "carla": {"managed_server": True}})
                def allocated(output):
                    # Checkpoint before starting any engine. A host/process crash
                    # must not leave a pair unreferenced by the batch manifest.
                    slot["attempts"].append({calibration_key:lead,"path":str(output),"passed":None})
                    write_json(manifest_path,manifest)
                output, report = run_pair(config,on_allocated=allocated)
                new_attempts += 1
                next(a for a in slot["attempts"] if a["path"]==str(output))["passed"] = report["passed"]
                if report["passed"]:
                    slot["selected"] = str(output)
                write_json(manifest_path, manifest)
                state = json.loads((output/"pair.json").read_text(encoding="utf-8"))["status"]
                if state == "failed":
                    manifest.update(status="interrupted", error="Infrastructure/worker failure; resume after restoring the server")
                    report = {"passed": False, "accepted_pairs": sum(s["selected"] is not None for s in manifest["samples"]),
                              "planned_pairs": len(samples), "error": manifest["error"], "samples": manifest["samples"]}
                    write_json(manifest_path, manifest)
                    write_json(directory/"validation.json", report)
                    return directory, report
                if max_new_attempts is not None and new_attempts >= max_new_attempts:
                    accepted = sum(s["selected"] is not None for s in manifest["samples"])
                    manifest.update(status="partial",accepted_pairs=accepted)
                    report = {"schema_version":2,"passed":False,"status":"partial","accepted_pairs":accepted,
                              "planned_pairs":len(samples),"attempt_budget_exhausted":True,"samples":manifest["samples"],
                              "repeatability":{"passed":False,"reason":"pending"}}
                    write_json(manifest_path,manifest)
                    write_json(directory/"validation.json",report)
                    return directory,report
                if report["passed"]:
                    break
        baseline = next(s for s in manifest["samples"] if s["parameters"] == batch["baseline"])
        if baseline["selected"]:
            manifest["baseline_selected"] = baseline["selected"]
            selected = json.loads((Path(baseline["selected"])/"pair.json").read_text(encoding="utf-8"))
            repeat_config = load_pair_config(scenario_path, selected["common_config"])
            good_repeats = [p for p in manifest["baseline_repeats"] if evaluate_pair(p)["passed"]]
            for _ in range(max(0, batch["baseline_runs"]-1-len(good_repeats))):
                def repeat_allocated(output):
                    manifest["baseline_repeats"].append(str(output))
                    write_json(manifest_path,manifest)
                output, report = run_pair(repeat_config,on_allocated=repeat_allocated)
                new_attempts += 1
                if report["passed"]:
                    good_repeats.append(str(output))
                write_json(manifest_path, manifest)
                state = json.loads((output/"pair.json").read_text(encoding="utf-8"))["status"]
                if state == "failed":
                    manifest.update(status="interrupted", error="Baseline worker failed; resume after restoring the server")
                    write_json(manifest_path, manifest)
                    report = {"passed":False,"accepted_pairs":sum(s["selected"] is not None for s in manifest["samples"]),
                              "planned_pairs":len(samples),"error":manifest["error"],"samples":manifest["samples"]}
                    write_json(directory/"validation.json",report)
                    return directory,report
                if max_new_attempts is not None and new_attempts >= max_new_attempts:
                    accepted = sum(s["selected"] is not None for s in manifest["samples"])
                    manifest.update(status="partial",accepted_pairs=accepted)
                    report = {"schema_version":2,"passed":False,"status":"partial","accepted_pairs":accepted,
                              "planned_pairs":len(samples),"attempt_budget_exhausted":True,"samples":manifest["samples"],
                              "repeatability":{"passed":False,"reason":"pending"}}
                    write_json(manifest_path,manifest)
                    write_json(directory/"validation.json",report)
                    return directory,report
            repeat_report = evaluate_repeats([baseline["selected"], *good_repeats], base.data["acceptance"]["repeat_event_tolerance_seconds"])
        else:
            repeat_report = {"passed": False, "reason": "no_accepted_baseline"}
        accepted = sum(s["selected"] is not None for s in manifest["samples"])
        manifest.update(status="passed" if accepted == len(samples) and repeat_report["passed"] else "incomplete", accepted_pairs=accepted)
        report = {"schema_version": 2, "passed": manifest["status"] == "passed", "accepted_pairs": accepted,
                  "planned_pairs": len(samples), "repeatability": repeat_report, "samples": manifest["samples"]}
        write_json(manifest_path, manifest)
        write_json(directory/"validation.json", report)
        return directory, report
    finally:
        lock.unlink()
