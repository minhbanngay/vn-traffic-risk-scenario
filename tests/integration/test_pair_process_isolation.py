import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from vn_traffic_risk.core import pairing
from vn_traffic_risk.core.config import PROJECT_ROOT, load_pair_config
from vn_traffic_risk.recording.recorder import write_json


@pytest.mark.parametrize("failure",[None,"R","CF"])
def test_fresh_owned_engine_surrounds_each_sdk_worker_and_is_closed(tmp_path,monkeypatch,failure):
    events = []
    class Scope:
        active = False
        def __enter__(self):
            self.active = True
            events.append("server_started")
        def __exit__(self,*args):
            events.append("server_stopped")
            self.active = False
    scope = Scope()
    monkeypatch.setattr(pairing,"server_scope",lambda config:scope)
    def run(command,**kwargs):
        if command[0]=="git":
            return SimpleNamespace(stdout="fixture",returncode=0)
        assert scope.active
        payload = json.loads(Path(command[-1]).read_text(encoding="utf-8"))
        if "--plan" in command:
            events.append("planning_worker")
            write_json(Path(payload["destination"]),{"frozen":"fixture"})
            return SimpleNamespace(returncode=0)
        branch = payload["branch"]
        events.append(branch+"_worker")
        if branch==failure:
            return SimpleNamespace(returncode=1)
        directory = Path(payload["directory"])
        directory.mkdir()
        write_json(directory/"episode.json",{"status":"complete"})
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(pairing.subprocess,"run",run)
    monkeypatch.setattr(pairing,"evaluate_pair",lambda directory:{"passed":failure is None})
    monkeypatch.setattr(pairing,"write_review",lambda directory:None)
    config = load_pair_config(PROJECT_ROOT/"configs/scenarios/group_a/INT-01.yaml",{"recording":{"output_root":str(tmp_path)}})
    directory,report = pairing.run_pair(config)
    assert events==["server_started","planning_worker","server_stopped",
                    "server_started","R_worker","server_stopped",
                    "server_started","CF_worker","server_stopped"]
    assert report["passed"] is (failure is None)
    manifest = json.loads((directory/"pair.json").read_text(encoding="utf-8"))
    assert manifest["status"] == ("passed" if failure is None else "failed")
