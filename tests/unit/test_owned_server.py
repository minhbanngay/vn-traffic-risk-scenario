from contextlib import nullcontext

import pytest

from vn_traffic_risk.runtime import server


def test_existing_server_is_never_replaced(monkeypatch):
    monkeypatch.setattr(server.socket,"create_connection",lambda *args,**kwargs:nullcontext())
    calls = []
    monkeypatch.setattr(server.subprocess,"Popen",lambda *args,**kwargs:calls.append(args))
    with pytest.raises(RuntimeError,match="existing server preserved"):
        server.ManagedServer({"host":"127.0.0.1","port":2000}).__enter__()
    assert calls == []


def test_owned_server_waits_then_only_terminates_its_own_process(tmp_path,monkeypatch):
    executable = tmp_path/"CarlaUE4.exe"
    executable.write_bytes(b"test fixture, not executable")
    connections = []
    def connect(*args,**kwargs):
        connections.append(args)
        if len(connections)==1:
            raise ConnectionRefusedError()
        return nullcontext()
    class Process:
        stopped = False
        def poll(self): return None
        def terminate(self): self.stopped = True
        def wait(self,timeout): return 0
    process = Process()
    monkeypatch.setattr(server.socket,"create_connection",connect)
    commands = []
    def launch(command,**kwargs):
        commands.append(command)
        return process
    monkeypatch.setattr(server.subprocess,"Popen",launch)
    monkeypatch.setattr(server.subprocess,"run",lambda *args,**kwargs:type("Ready",(),{"returncode":0})())
    with server.ManagedServer({"host":"127.0.0.1","port":2000,"server_executable":str(executable),"server_max_fps":20}):
        assert not process.stopped
    assert process.stopped and len(connections)==2
    assert "-ExecCmds=t.MaxFPS 20" in commands[0]


def test_managed_server_refuses_remote_host():
    with pytest.raises(ValueError,match="localhost"):
        server.ManagedServer({"host":"192.0.2.1","port":2000}).__enter__()
