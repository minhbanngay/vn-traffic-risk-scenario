"""Read-only GPU telemetry and a precautionary guard for an owned engine.

This is not a hardware diagnostic or a guarantee against power/driver failures.
It never changes GPU clocks, power limits, drivers or system settings.
"""
from datetime import datetime, timezone
import csv
import io
import json
import os
from pathlib import Path
import subprocess
import threading


def gpu_sample():
    fields = ["uuid", "name", "driver_version", "temperature.gpu", "memory.total",
              "memory.used", "utilization.gpu", "power.draw"]
    result = subprocess.run(["nvidia-smi", "--query-gpu="+",".join(fields),
                             "--format=csv,noheader,nounits"], capture_output=True,
                            text=True, check=True, timeout=5,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    gpus = []
    for row in csv.reader(io.StringIO(result.stdout)):
        if len(row) != len(fields):
            raise ValueError("Unexpected nvidia-smi telemetry columns")
        values = dict(zip(fields, (cell.strip() for cell in row)))
        for key in fields[3:]:
            values[key] = None if values[key] in {"[N/A]", "N/A", "[Not Supported]"} else float(values[key])
        if values["temperature.gpu"] is None or not values["memory.total"] or values["memory.used"] is None:
            raise ValueError("GPU temperature/VRAM telemetry unavailable")
        gpus.append(values)
    if not gpus:
        raise ValueError("No GPU telemetry returned")
    return gpus


class EngineHealthMonitor:
    def __init__(self, config, path, stop_owned):
        self.config, self.stop_owned = config, stop_owned
        self.path = Path(path) if path else None
        self.failure = None
        self.stopped = threading.Event()
        self.thread = None
        self.stream = None
        self.errors = 0

    def _record(self, value):
        if self.stream:
            self.stream.write(json.dumps({"utc":datetime.now(timezone.utc).isoformat(), **value}, allow_nan=False)+"\n")
            self.stream.flush()

    def sample(self):
        try:
            gpus = gpu_sample()
            self.errors = 0
            self._record({"event":"gpu_sample", "gpus":gpus})
            for gpu in gpus:
                if gpu["temperature.gpu"] >= self.config["max_gpu_temperature_c"]:
                    self.failure = f'GPU temperature guard: {gpu["temperature.gpu"]} C'
                if gpu["memory.used"]/gpu["memory.total"] >= self.config["max_vram_fraction"]:
                    self.failure = f'GPU VRAM guard: {gpu["memory.used"]}/{gpu["memory.total"]} MiB'
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            self.errors += 1
            self._record({"event":"gpu_probe_error", "error":str(exc), "consecutive_errors":self.errors})
            if self.errors >= self.config.get("max_probe_errors",3):
                self.failure = "GPU telemetry repeatedly unavailable"
        if self.failure:
            self._record({"event":"health_guard_stop", "error":self.failure})
            self.stop_owned()
            self.stopped.set()

    def start(self):
        if self.path:
            self.stream = self.path.open("x",encoding="utf-8")
        # Require a working, below-threshold sample BEFORE launching the engine.
        self.sample()
        if self.errors or self.failure:
            self.close()
            raise RuntimeError(self.failure or "Initial GPU telemetry unavailable; engine not started")
        def monitor():
            while not self.stopped.wait(self.config["interval_seconds"]):
                self.sample()
        self.thread = threading.Thread(target=monitor,name="owned-engine-health",daemon=True)
        self.thread.start()

    def check(self):
        if self.failure:
            raise RuntimeError(self.failure)

    def close(self):
        self.stopped.set()
        if self.thread:
            self.thread.join(timeout=10)
        if self.stream:
            self.stream.close()
            self.stream = None
