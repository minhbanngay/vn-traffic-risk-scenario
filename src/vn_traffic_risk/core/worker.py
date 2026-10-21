"""One CARLA client process per episode, isolating native API lifetime failures."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import os
import traceback
import copy

from .runner import run_episode
from ..runtime.session import PairSession
from .registry import get_scenario
from ..recording.recorder import write_json
from ..carla_runtime import require_carla
from .config import fingerprint, implementation_fingerprint


def main():
    if sys.argv[1] == "--ready":
        carla = require_carla()
        client = carla.Client(sys.argv[2], int(sys.argv[3]))
        client.set_timeout(float(sys.argv[4]))
        client.get_world().get_map()
        return 0
    if sys.argv[1] == "--plan":
        payload = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
        planning_config = copy.deepcopy(payload["config"])
        # Waypoint discovery needs no simulation stepping. Never leave a world
        # waiting for a synchronous cue before the next SDK client subscribes.
        planning_config["carla"]["synchronous_mode"] = False
        with PairSession(planning_config) as session:
            scenario = get_scenario(payload["config"]["scenario"]["scenario_id"])
            layout = scenario.plan(session.world, payload["config"])
            layout = scenario.freeze_intervention(session, payload["config"], layout)
            write_json(Path(payload["destination"]), layout)
        return 0
    payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    with PairSession(payload["config"]) as session:
        summary = run_episode(session, payload["config"], payload["layout"], payload["branch"],
                              Path(payload["directory"]), payload["identity"])
    return 0 if summary["status"] == "complete" else 1


if __name__ == "__main__":
    try:
        code = main()
    except BaseException:
        traceback.print_exc()
        code = 1
    sys.stdout.flush()
    sys.stderr.flush()
    if os.name == "nt":
        # All application scopes have already exited and files are closed.
        # Avoid libcarla's native static/thread teardown during Python shutdown.
        os._exit(code)
    raise SystemExit(code)
