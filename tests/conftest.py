"""Synthetic acceptance fixtures; never used as collected CARLA data."""
from pathlib import Path

from PIL import Image
import pytest

from vn_traffic_risk.core.config import PROJECT_ROOT, fingerprint, load_pair_config
from vn_traffic_risk.evaluation.risk import observe
from vn_traffic_risk.models import ActorState, Vec3
from vn_traffic_risk.recording.recorder import EpisodeRecorder, write_json


@pytest.fixture
def recorded_pair(tmp_path):
    config = load_pair_config(PROJECT_ROOT/"configs/scenarios/group_a/INT-01.yaml",
                              {"recording":{"image_width":8,"image_height":4,"create_video":False}})
    directory = tmp_path/"pair"
    directory.mkdir()
    layout = {"ego_route":[{"x":0,"y":0,"z":0},{"x":200,"y":0,"z":0}]}
    identity = {"schema_version":2,"scenario_id":"INT-01","pair_id":config.pair_id,"attempt_id":"fixture"}
    write_json(directory/"pair.json", {**identity,"common_config":config.data,
                                      "config_fingerprint":fingerprint(config.data),"layout_fingerprint":fingerprint(layout)})
    for branch in ("R","CF"):
        recorder = EpisodeRecorder(directory/branch, config.branch(branch), layout, {**identity,"branch":branch})
        def state(role,x,y,speed):
            return ActorState(1 if role=="ego" else 2,role,"vehicle.test",Vec3(x,y),Vec3(0,0),
                              Vec3(speed,0),Vec3(0,0),speed,1,1,Vec3(2,1,1))
        for index in range(130):
            ego_speed = 5.0 if branch=="R" and index>=15 else 7.0
            ego = state("ego",index*0.35,0,ego_speed)
            active = index>=5 if branch=="R" else index>=6
            actor = state("primary_risk_actor",ego.location.x+(6 if branch=="R" else -22) if active else ego.location.x-8,
                          0 if active else -3.5,7)
            frame_id = (1000 if branch=="R" else 3000)+index
            relative = f"rgb/{frame_id:08d}.jpg"
            Image.new("RGB",(8,4)).save(directory/branch/relative)
            recorder.append({**identity,"branch":branch,"step_index":index,"frame_id":frame_id,"timestamp":index*0.05,
                             "relative_time_seconds":index*0.05,"rgb_file":relative,"ego":ego.as_dict(),"actors":[actor.as_dict()],
                             "risk":observe(ego,actor,(1,0),config.data["risk_labelling"]),
                             "controls":{"ego":{"brake":0.15 if branch=="R" and index>=15 else 0}},
                             "maneuver_state":"completed" if index>=20 else "merging" if active else "approaching",
                             "sensor":{"image_frame_id":frame_id}})
        for event, step in (("intervention",5),("merge_started",5 if branch=="R" else 6),("merge_completed",20)):
            recorder.event({"event":event,"step_index":step})
        if branch=="R":
            recorder.event({"event":"ego_response_triggered","step_index":5,"speed_mps":7})
        recorder.finalize([])
        recorder.close()
    return directory
