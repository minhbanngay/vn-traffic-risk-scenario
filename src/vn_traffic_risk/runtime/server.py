"""Optional owned CARLA process; never terminates a pre-existing server."""
from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path
import os
import socket
import subprocess
import sys
import time

from ..core.config import PROJECT_ROOT
from .health import EngineHealthMonitor


class ManagedServer:
    def __init__(self, config):
        self.config = config
        self.process = None
        self.monitor = None

    def __enter__(self):
        host, port = self.config["host"], self.config["port"]
        if host not in {"127.0.0.1", "localhost"}:
            raise ValueError("Managed CARLA is restricted to localhost")
        try:
            with socket.create_connection((host, port), timeout=0.5):
                raise RuntimeError("Managed server port is occupied; existing server preserved")
        except (ConnectionRefusedError, TimeoutError, socket.timeout):
            pass
        executable = self.config.get("server_executable") or str(PROJECT_ROOT.parents[1]/"CarlaUE4/Binaries/Win64/CarlaUE4-Win64-Shipping.exe")
        if not Path(executable).is_file():
            raise ValueError(f"CARLA server executable not found: {executable}")
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        try:
            health = self.config.get("health_monitor",{})
            if health.get("enabled"):
                self.monitor = EngineHealthMonitor(health,self.config.get("telemetry_path"),self._stop_owned)
                self.monitor.start()
            command = [executable, "-RenderOffScreen", "-quality-level=Low", "-nosound", "-unattended",
                       "-ResX=640", "-ResY=360", f"-carla-rpc-port={port}"]
            if self.config.get("server_max_fps"):
                command.append(f'-ExecCmds=t.MaxFPS {float(self.config["server_max_fps"]):g}')
            self.process = subprocess.Popen(command,cwd=PROJECT_ROOT.parents[1],creationflags=flags,
                                            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            deadline = time.monotonic()+self.config.get("startup_timeout_seconds", 90)
            while time.monotonic() < deadline:
                if self.monitor:
                    self.monitor.check()
                if self.process.poll() is not None:
                    raise RuntimeError(f"Owned CARLA exited during startup: {self.process.returncode}")
                try:
                    with socket.create_connection((host, port), timeout=1.0):
                        remaining = max(1.0, deadline-time.monotonic())
                        ready = subprocess.run([sys.executable, "-m", "vn_traffic_risk.core.worker", "--ready", host, str(port), str(remaining)],
                                               cwd=PROJECT_ROOT, timeout=remaining+5, check=False)
                        if ready.returncode:
                            raise RuntimeError(f"CARLA world readiness worker failed: {ready.returncode}")
                        if self.monitor:
                            self.monitor.check()
                        return self
                except (ConnectionRefusedError, TimeoutError, socket.timeout):
                    time.sleep(0.5)
            raise RuntimeError("Owned CARLA did not become ready before startup timeout")
        except BaseException:
            self.__exit__()
            raise

    def _stop_owned(self):
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()

    def __exit__(self, *args):
        if self.monitor:
            self.monitor.close()
        if self.process is not None and self.process.poll() is None:
            self._stop_owned()
            try:
                self.process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=10)
        if self.monitor and (not args or args[0] is None):
            self.monitor.check()


def server_scope(config):
    return ManagedServer(config) if config.get("managed_server", False) else nullcontext()
