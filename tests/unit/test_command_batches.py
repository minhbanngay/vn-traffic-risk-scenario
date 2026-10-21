from types import SimpleNamespace

import pytest

from vn_traffic_risk.runtime import commands


def fake_carla():
    return SimpleNamespace(command=SimpleNamespace(ApplyVehicleControl=lambda actor,control:("control",actor,control),
                                                   ApplyTargetVelocity=lambda actor,velocity:("velocity",actor,velocity)),
                           VehicleControl=lambda: "released_brake",Vector3D=lambda **values:values)


def test_controls_are_acknowledged_without_an_extra_tick(monkeypatch):
    monkeypatch.setattr(commands,"require_carla",fake_carla)
    submitted = []
    def send(batch,tick):
        submitted.append((batch,tick))
        return [SimpleNamespace(error="") for _ in batch]
    commands.apply_controls(SimpleNamespace(apply_batch_sync=send),{"ego":SimpleNamespace(id=7)},{"ego":"brake"})
    assert submitted==[([("control",7,"brake")],False)]


def test_failed_control_command_stops_collection(monkeypatch):
    monkeypatch.setattr(commands,"require_carla",fake_carla)
    client = SimpleNamespace(apply_batch_sync=lambda *args:[SimpleNamespace(error="actor missing")])
    with pytest.raises(RuntimeError,match="command batch failed"):
        commands.apply_controls(client,{"ego":SimpleNamespace(id=7)},{"ego":"brake"})


def test_initial_motion_uses_frozen_heading_and_one_batch(monkeypatch):
    monkeypatch.setattr(commands,"require_carla",fake_carla)
    submitted = []
    def send(batch,tick):
        submitted.append((batch,tick))
        return [SimpleNamespace(error="") for _ in batch]
    transforms = {"ego":SimpleNamespace(rotation=SimpleNamespace(get_forward_vector=lambda:SimpleNamespace(x=0,y=-1,z=0)))}
    commands.initialize_motion(SimpleNamespace(apply_batch_sync=send),{"ego":SimpleNamespace(id=7)},transforms,{"ego":10})
    assert submitted[0][1] is False
    assert submitted[0][0][1] == ("velocity",7,{"x":0,"y":-10,"z":0})
