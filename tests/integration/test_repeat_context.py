import json
import shutil

import pytest

from vn_traffic_risk.core.batch import evaluate_repeats
from vn_traffic_risk.core.config import fingerprint
from vn_traffic_risk.recording.recorder import write_json


@pytest.mark.parametrize("change_static",[False,True])
def test_repeat_context_ignores_reference_actor_ids_but_not_route_changes(recorded_pair,tmp_path,change_static):
    attempts = []
    for index in range(3):
        destination = tmp_path/f"repeat{index}"
        shutil.copytree(recorded_pair,destination)
        layout = json.loads((destination/"R/layout.json").read_text(encoding="utf-8"))
        layout["intervention_reference"] = {"source":"common_approach_rehearsal","actor_id":100+index}
        layout["intervention_step_index"] = 5
        if index==2 and change_static:
            layout["ego_route"][-1]["x"] = 220
        for branch in ("R","CF"):
            write_json(destination/branch/"layout.json",layout)
        manifest = json.loads((destination/"pair.json").read_text(encoding="utf-8"))
        manifest["layout_fingerprint"] = fingerprint(layout)
        write_json(destination/"pair.json",manifest)
        attempts.append(destination)
    assert evaluate_repeats(attempts,0.15)["passed"] is (not change_static)
