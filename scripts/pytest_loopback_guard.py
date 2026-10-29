"""Temporary first-party test guard: Python loopback sockets only, not an OS sandbox."""
import ipaddress
import json
import os
from pathlib import Path
import socket

_attempts = []
_originals = {}

def _check(host):
    if isinstance(host, bytes):
        host = host.decode("ascii", errors="replace")
    if host is None or host == "localhost":
        return
    try:
        if ipaddress.ip_address(host).is_loopback:
            return
    except (ValueError, TypeError):
        pass
    _attempts.append("non_loopback")
    raise OSError("Non-loopback network access forbidden during merge acceptance")

def pytest_sessionstart(session):
    _originals["connect"] = socket.socket.connect
    _originals["connect_ex"] = socket.socket.connect_ex
    _originals["sendto"] = socket.socket.sendto
    _originals["getaddrinfo"] = socket.getaddrinfo
    def connect(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6): _check(address[0])
        return _originals["connect"](sock, address)
    def connect_ex(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6): _check(address[0])
        return _originals["connect_ex"](sock, address)
    def sendto(sock, *args):
        if sock.family in (socket.AF_INET, socket.AF_INET6): _check(args[-1][0])
        return _originals["sendto"](sock, *args)
    def getaddrinfo(host, *args, **kwargs):
        _check(host)
        return _originals["getaddrinfo"](host, *args, **kwargs)
    socket.socket.connect = connect
    socket.socket.connect_ex = connect_ex
    socket.socket.sendto = sendto
    socket.getaddrinfo = getaddrinfo

def pytest_sessionfinish(session, exitstatus):
    for name in ("connect", "connect_ex", "sendto"): setattr(socket.socket, name, _originals[name])
    socket.getaddrinfo = _originals["getaddrinfo"]
    if _attempts: session.exitstatus = 1
    Path(os.environ["CASCADE_MERGE_NETWORK_REPORT"]).write_text(json.dumps({
        "non_loopback_attempts": len(_attempts), "scope": "Python DNS/connect/connect_ex/sendto; child processes not instrumented",
        "provider_sdk_imports": sorted(name for name in ("openai", "nebius", "tavily") if name in __import__("sys").modules)
    })+"\n", encoding="utf-8")
    session.config.pluginmanager.get_plugin("terminalreporter").write_line("Merge network guard: %d non-loopback attempts" % len(_attempts))
