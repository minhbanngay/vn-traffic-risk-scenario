import importlib.util
from pathlib import Path

from vn_traffic_risk.core.config import PROJECT_ROOT


spec = importlib.util.spec_from_file_location("pilot_audit",PROJECT_ROOT/"scripts/audit_pilot.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def row(index,x):
    def actor(position):
        return {"actor_id":1,"role_name":"test","type_id":"test", "location":{"x":position,"y":0,"z":0},
                "rotation":{"x":0,"y":0,"z":0},"velocity":{"x":5,"y":0,"z":0},
                "acceleration":{"x":0,"y":0,"z":0},"speed_mps":5,"road_id":1,"lane_id":1,
                "bbox_extent":{"x":1,"y":0.5,"z":1}}
    return {"step_index":index,"ego":actor(x),"actors":[actor(x+10)]}


def test_route_tail_audit_rejects_reversing_after_completion():
    layout = {"ego_route":[{"x":0,"y":0,"z":0},{"x":100,"y":0,"z":0}]}
    assert audit.route_tail_audit([row(0,10),row(1,11)],layout,0)["passed"]
    assert not audit.route_tail_audit([row(0,10),row(1,9)],layout,0)["passed"]


def test_video_audit_checks_final_decoded_frame_count(monkeypatch):
    import sys
    from types import SimpleNamespace
    monkeypatch.setitem(sys.modules,"imageio_ffmpeg",SimpleNamespace(get_ffmpeg_exe=lambda:"fixture-ffmpeg"))
    monkeypatch.setattr(audit.subprocess,"run",lambda *args,**kwargs:SimpleNamespace(returncode=0,stdout="frame=1\nframe=198\n",stderr=""))
    assert audit.decoded_video_frames(Path("fixture.mp4")) == 198
