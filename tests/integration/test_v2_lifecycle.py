from types import SimpleNamespace

from vn_traffic_risk.core.config import PROJECT_ROOT, load_pair_config
from vn_traffic_risk.recording.recorder import EpisodeRecorder, read_jsonl
from vn_traffic_risk.runtime.sensors import RGBFrameBuffer
from vn_traffic_risk.runtime.session import ActorScope, spawn_exact


def test_frame_buffer_keeps_future_image_and_logs_missing():
    buffer = RGBFrameBuffer()
    image = SimpleNamespace(frame=11)
    buffer.callback(image)
    assert buffer.get(10, 0) is None
    assert buffer.get(11, 0.01) is image
    assert buffer.diagnostics[1] == {"event": "rgb_timeout", "frame_id": 10}


def test_scope_cleans_up_in_reverse_even_if_next_spawn_fails():
    destroyed = []
    scope = ActorScope()
    scope.add(SimpleNamespace(is_alive=True, destroy=lambda: destroyed.append("ego")))
    scope.add(SimpleNamespace(is_alive=True, destroy=lambda: destroyed.append("camera")))
    scope.close()
    assert destroyed == ["camera", "ego"]


def test_duplicate_received_after_consumption_is_still_detected():
    buffer = RGBFrameBuffer()
    image = SimpleNamespace(frame=11)
    buffer.callback(image)
    assert buffer.get(11,0.01) is image
    buffer.callback(image)
    assert buffer.diagnostics[-1]["duplicate"]


def test_durable_raw_records_and_delayed_collision_reconciliation(tmp_path):
    config = load_pair_config(PROJECT_ROOT/"configs/scenarios/group_a/INT-01.yaml").branch("R")
    recorder = EpisodeRecorder(tmp_path/"R", config, {}, {"branch": "R"})
    for step in range(3):
        recorder.append({"step_index":step, "frame_id":100+step, "rgb_file":None,
                         "risk":{"is_risk":False,"reasons":[]}})
    assert len(read_jsonl(tmp_path/"R/frames.raw.jsonl")) == 3
    summary = recorder.finalize([{"frame":101}], status="complete")
    recorder.close()
    frames = read_jsonl(tmp_path/"R/frames.jsonl")
    assert summary["status"] == "incomplete"
    assert frames[1]["risk"]["collision_now"]
    assert not frames[2]["risk"]["collision_now"]
    assert frames[2]["risk"]["collision_occurred"]
    assert frames[-1]["future_risk_valid"] == [False]*8
