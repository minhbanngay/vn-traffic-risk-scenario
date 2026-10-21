import json
from pathlib import Path

import pytest

from vn_traffic_risk.core import batch
from vn_traffic_risk.core.config import PROJECT_ROOT, load_pair_config, merge
from vn_traffic_risk.core.pairing import allocate_attempt
from vn_traffic_risk.recording.recorder import write_json


def test_attempt_allocator_never_overwrites_existing_data(tmp_path):
    a = allocate_attempt(tmp_path/"pair")
    (a/"evidence.txt").write_text("preserve")
    b = allocate_attempt(tmp_path/"pair")
    assert a != b and (a/"evidence.txt").read_text() == "preserve"


@pytest.mark.parametrize("budget",[None,1])
def test_batch_resumes_without_repeating_accepted_pairs(tmp_path, monkeypatch,budget):
    calls = []
    original_loader = load_pair_config
    def loader(path, overrides=None):
        return original_loader(path, merge(overrides or {}, {"recording":{"output_root":str(tmp_path)}}))
    def run(config,on_allocated=None):
        path = allocate_attempt(tmp_path/"INT-01"/config.pair_id)
        write_json(path/"pair.json", {"status":"passed","common_config":config.data})
        if on_allocated:
            on_allocated(path)
        calls.append(path)
        return path, {"passed":True}
    monkeypatch.setattr(batch,"load_pair_config",loader)
    monkeypatch.setattr(batch,"run_pair",run)
    monkeypatch.setattr(batch,"evaluate_pair",lambda path:{"passed":True})
    monkeypatch.setattr(batch,"evaluate_repeats",lambda paths,tolerance:{"passed":len(paths)==3})
    path, first = batch.run_batch(PROJECT_ROOT/"configs/batches/int_01_pilot.yaml",max_new_attempts=budget)
    if budget:
        assert not first["passed"] and first["status"] == "partial"
        assert first["accepted_pairs"] == len(calls) == 1
    else:
        assert first["passed"] and first["accepted_pairs"] == 10 and len(calls) == 12
    _, resumed = batch.run_batch(PROJECT_ROOT/"configs/batches/int_01_pilot.yaml")
    assert resumed["passed"] and len(calls) == 12
    assert not (path/"batch.lock").exists()


def test_batch_checkpoints_allocated_attempt_before_worker_can_be_interrupted(tmp_path,monkeypatch):
    original_loader = load_pair_config
    monkeypatch.setattr(batch,"load_pair_config",lambda path,overrides=None:original_loader(
        path,merge(overrides or {},{"recording":{"output_root":str(tmp_path)}})))
    allocated = []
    def interrupted(config,on_allocated):
        output = allocate_attempt(tmp_path/"INT-01"/config.pair_id)
        write_json(output/"pair.json",{"status":"running"})
        on_allocated(output)
        allocated.append(output)
        raise RuntimeError("simulated host/process interruption")
    monkeypatch.setattr(batch,"run_pair",interrupted)
    with pytest.raises(RuntimeError,match="simulated host/process interruption"):
        batch.run_batch(PROJECT_ROOT/"configs/batches/int_01_pilot.yaml")
    manifest = json.loads((tmp_path/"batches/int_01_pilot/manifest.json").read_text(encoding="utf-8"))
    attempt = manifest["samples"][0]["attempts"][0]
    assert attempt["path"] == str(allocated[0])
    assert attempt["passed"] is None
    assert json.loads((allocated[0]/"pair.json").read_text(encoding="utf-8"))["status"] == "running"


def test_attempt_budget_also_applies_to_baseline_repeats(tmp_path, monkeypatch):
    original_loader = load_pair_config
    calls = []
    monkeypatch.setattr(batch, "load_pair_config", lambda path, overrides=None: original_loader(
        path, merge(overrides or {}, {"recording": {"output_root": str(tmp_path)}})))
    monkeypatch.setattr(batch, "runtime_environment", lambda: {"fixture": True})

    def run(config, on_allocated=None):
        path = allocate_attempt(tmp_path/"INT-08"/config.pair_id)
        write_json(path/"pair.json", {"status": "passed", "common_config": config.data})
        on_allocated(path)
        calls.append(path)
        return path, {"passed": True}

    monkeypatch.setattr(batch, "run_pair", run)
    monkeypatch.setattr(batch, "evaluate_pair", lambda path: {"passed": True})
    monkeypatch.setattr(batch, "evaluate_repeats", lambda paths, tolerance: {"passed": len(paths) == 3})
    source = PROJECT_ROOT/"configs/batches/int_08_pilot_managed.yaml"
    path, report = batch.run_batch(source)
    assert report["passed"] and len(calls) == 5
    # Model a checkpoint where all matrix samples passed but repeats are pending.
    manifest = json.loads((path/"manifest.json").read_text(encoding="utf-8"))
    manifest["baseline_repeats"] = []
    write_json(path/"manifest.json", manifest)
    before = len(calls)
    _, partial = batch.run_batch(source, max_new_attempts=1)
    assert partial["status"] == "partial" and len(calls) == before+1
    assert not (path/"batch.lock").exists()
    _, final = batch.run_batch(source, max_new_attempts=1)
    # One last repeat can checkpoint partial; a read-only resume finalizes it.
    assert len(calls) == before+2
    _, final = batch.run_batch(source)
    assert final["passed"] and len(calls) == before+2
