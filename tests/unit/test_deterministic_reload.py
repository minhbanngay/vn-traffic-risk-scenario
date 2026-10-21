from types import SimpleNamespace

from vn_traffic_risk.core.config import PROJECT_ROOT, load_pair_config
from vn_traffic_risk.runtime.session import PairSession


def test_reload_keeps_sync_from_first_frame_without_async_interval():
    config = load_pair_config(PROJECT_ROOT/"configs/scenarios/group_a/INT-01.yaml").data
    calls = []
    world = SimpleNamespace(get_settings=lambda:SimpleNamespace(synchronous_mode=True,fixed_delta_seconds=0.05))
    def reload(reset):
        calls.append(reset)
        return world
    scope = PairSession(config)
    scope.manager = SimpleNamespace(client=SimpleNamespace(reload_world=reload),world=None,apply_weather=lambda weather:None)
    assert scope.reset() is world
    assert calls == [False] and scope.manager.world is world
