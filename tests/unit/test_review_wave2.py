import json

import pytest

from vn_traffic_risk.recording.report import write_review


@pytest.mark.parametrize("lateral", [False, True])
def test_review_includes_actor_speed_and_scenario_geometry(tmp_path, lateral):
    branch = tmp_path/"R"
    branch.mkdir()
    risk = {"bumper_gap_m": 8, "corridor_overlap": False, "time_headway_seconds": 2,
            "ttc_seconds": 3, "is_risk": lateral}
    if lateral:
        risk["lateral_clearance_m"] = 0.3
    row = {"relative_time_seconds": 0.05, "ego": {"speed_mps": 7}, "actors": [{"speed_mps": 6}], "risk": risk}
    (branch/"frames.jsonl").write_text(json.dumps(row)+"\n", encoding="utf-8")
    write_review(tmp_path)
    html = (tmp_path/"review.html").read_text(encoding="utf-8")
    assert "Primary actor speed" in html and "Closing TTC" in html
    assert ("Lateral body clearance" in html) is lateral
