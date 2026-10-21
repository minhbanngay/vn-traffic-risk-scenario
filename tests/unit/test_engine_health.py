import json
from types import SimpleNamespace

import pytest

from vn_traffic_risk.runtime import health


CONFIG = {"interval_seconds":5,"max_gpu_temperature_c":82,"max_vram_fraction":0.97,"max_probe_errors":3}


def gpu(temperature=50, used=2000):
    return {"temperature.gpu":temperature,"memory.used":used,"memory.total":6000}


def test_gpu_csv_is_read_only_and_numeric(monkeypatch):
    calls = []
    def run(command,**kwargs):
        calls.append(command)
        return SimpleNamespace(stdout='GPU-1, NVIDIA GPU, 616.92, 44, 6144, 420, 0, [N/A]\n')
    monkeypatch.setattr(health.subprocess,"run",run)
    sample = health.gpu_sample()[0]
    assert sample["temperature.gpu"] == 44 and sample["power.draw"] is None
    assert all(not arg.startswith(("-pl","-lgc","-pm")) for arg in calls[0])


@pytest.mark.parametrize("sample",[gpu(82),gpu(50,5900)])
def test_temperature_or_vram_guard_only_stops_owned_engine(tmp_path,monkeypatch,sample):
    monkeypatch.setattr(health,"gpu_sample",lambda:[sample])
    stopped = []
    path = tmp_path/"gpu.jsonl"
    monitor = health.EngineHealthMonitor(CONFIG,path,lambda:stopped.append("owned"))
    with pytest.raises(RuntimeError,match="GPU .* guard"):
        monitor.start()
    assert stopped == ["owned"]
    events = [json.loads(line) for line in path.read_text().splitlines()]
    assert events[-1]["event"] == "health_guard_stop"


def test_unavailable_initial_probe_prevents_engine_start(tmp_path,monkeypatch):
    def unavailable(): raise FileNotFoundError("nvidia-smi")
    monkeypatch.setattr(health,"gpu_sample",unavailable)
    monitor = health.EngineHealthMonitor(CONFIG,tmp_path/"gpu.jsonl",lambda:None)
    with pytest.raises(RuntimeError,match="Initial GPU telemetry unavailable"):
        monitor.start()
    assert monitor.stream is None and monitor.thread is None


def test_guard_logs_and_closes_on_healthy_run(tmp_path,monkeypatch):
    monkeypatch.setattr(health,"gpu_sample",lambda:[gpu()])
    stopped = []
    monitor = health.EngineHealthMonitor(CONFIG,tmp_path/"gpu.jsonl",lambda:stopped.append("owned"))
    monitor.start()
    monitor.close()
    assert not stopped and not monitor.thread.is_alive() and monitor.stream is None


def test_repeated_probe_errors_stop_owned_engine(tmp_path,monkeypatch):
    monkeypatch.setattr(health,"gpu_sample",lambda:[gpu()])
    stopped = []
    monitor = health.EngineHealthMonitor(CONFIG,None,lambda:stopped.append("owned"))
    def unavailable(): raise OSError("driver probe unavailable")
    monkeypatch.setattr(health,"gpu_sample",unavailable)
    for _ in range(3): monitor.sample()
    assert stopped == ["owned"]
    with pytest.raises(RuntimeError,match="telemetry repeatedly unavailable"):
        monitor.check()
