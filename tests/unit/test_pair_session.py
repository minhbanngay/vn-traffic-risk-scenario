from types import SimpleNamespace

import pytest

from vn_traffic_risk.core.config import PROJECT_ROOT, load_pair_config
from vn_traffic_risk.runtime import session as runtime


@pytest.mark.parametrize("managed",[False,True])
def test_fresh_engine_does_not_redundantly_reload_before_connect(monkeypatch,managed):
    config = load_pair_config(PROJECT_ROOT/"configs/scenarios/group_a/INT-01.yaml",
                              {"carla":{"managed_server":managed}}).data
    events = []
    actors = SimpleNamespace(filter=lambda pattern:[])
    world = SimpleNamespace(get_actors=lambda:actors,get_weather=lambda:"weather",set_weather=lambda value:None,
                            get_settings=lambda:SimpleNamespace(synchronous_mode=False),
                            apply_settings=lambda value:None,tick=lambda:events.append("handoff_tick"))
    client = SimpleNamespace(set_timeout=lambda value:None,
                             load_world=lambda *args:events.append("load"),
                             get_world=lambda:events.append("query") or world)
    monkeypatch.setattr(runtime,"require_carla",lambda:SimpleNamespace(Client=lambda *args:client))
    scope = runtime.PairSession(config)
    scope.manager = SimpleNamespace(connect=lambda **kwargs:events.append("connect") or world,
                                    apply_weather=lambda value:None,restore=lambda:events.append("restore"))
    with scope:
        assert scope.world is world
    assert "load" not in events
    assert events.index("query") < events.index("connect")
    assert "restore" in events
    assert "handoff_tick" not in events


def test_external_traffic_is_preserved_before_any_world_change(monkeypatch):
    config = load_pair_config(PROJECT_ROOT/"configs/scenarios/group_a/INT-01.yaml").data
    client = SimpleNamespace(set_timeout=lambda value:None,
                             get_world=lambda:SimpleNamespace(get_actors=lambda:SimpleNamespace(filter=lambda pattern:["existing_actor"])))
    monkeypatch.setattr(runtime,"require_carla",lambda:SimpleNamespace(Client=lambda *args:client))
    scope = runtime.PairSession(config)
    scope.manager = SimpleNamespace(connect=lambda:pytest.fail("Must not change a world with existing traffic"))
    with pytest.raises(RuntimeError,match="existing traffic was preserved"):
        scope.__enter__()
