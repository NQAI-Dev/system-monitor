"""Tests for the pure helper functions in main.py.

The live FastAPI app is exercised only via the helpers; psutil/os/subprocess
are monkeypatched so the suite runs without touching real host state.
"""
import os
import sys
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402


def _fake_proc_uptime(text):
    """Build a context-manager mock that returns `text` from .read()."""
    handle = MagicMock()
    handle.read.return_value = text
    cm = MagicMock()
    cm.__enter__.return_value = handle
    return cm


def test_get_uptime_parses_proc_uptime():
    with patch("builtins.open", return_value=_fake_proc_uptime("90061.5 1234.0\n")):
        out = main.get_uptime()
    assert out["total_seconds"] == pytest.approx(90061.5)
    assert out["days"] == 1
    assert out["hours"] == 1
    assert out["minutes"] == 1
    assert out["seconds"] == 1


def test_get_uptime_handles_subsecond():
    with patch("builtins.open", return_value=_fake_proc_uptime("0.5 0.0\n")):
        out = main.get_uptime()
    assert out["days"] == 0
    assert out["seconds"] == 0
    assert out["total_seconds"] == pytest.approx(0.5)


def test_get_disks_skips_permission_errors():
    fake_partition = MagicMock()
    fake_partition.device = "/dev/sda1"
    fake_partition.mountpoint = "/"
    fake_partition.fstype = "ext4"
    fake_usage = MagicMock()
    fake_usage.total = 1000
    fake_usage.used = 400
    fake_usage.free = 600
    fake_usage.percent = 40.0
    with patch("main.psutil.disk_partitions", return_value=[fake_partition]), \
         patch("main.psutil.disk_usage", return_value=fake_usage):
        out = main.get_disks()
    assert len(out) == 1
    assert out[0]["device"] == "/dev/sda1"
    assert out[0]["percent"] == 40.0


def test_get_disks_swallows_permissionerror():
    bad = MagicMock()
    bad.mountpoint = "/secret"
    with patch("main.psutil.disk_partitions", return_value=[bad]), \
         patch("main.psutil.disk_usage", side_effect=PermissionError):
        out = main.get_disks()
    assert out == []


def test_get_network_extracts_ipv4_and_counters():
    addr_v4 = MagicMock()
    addr_v4.family.name = "AF_INET"
    addr_v4.address = "10.0.0.1"
    addr_v6 = MagicMock()
    addr_v6.family.name = "AF_INET6"
    addr_v6.address = "fe80::1"
    counters = MagicMock()
    counters.bytes_sent = 1234
    counters.bytes_recv = 5678
    with patch("main.psutil.net_if_addrs", return_value={"eth0": [addr_v4, addr_v6]}), \
         patch("main.psutil.net_io_counters", return_value={"eth0": counters}):
        out = main.get_network()
    assert out == [{
        "interface": "eth0",
        "ipv4": "10.0.0.1",
        "ipv6": "fe80::1",
        "bytes_sent": 1234,
        "bytes_recv": 5678,
    }]


def test_get_network_zero_counters_when_missing():
    addr = MagicMock()
    addr.family.name = "AF_INET"
    addr.address = "127.0.0.1"
    with patch("main.psutil.net_if_addrs", return_value={"lo": [addr]}), \
         patch("main.psutil.net_io_counters", return_value={}):
        out = main.get_network()
    assert out[0]["bytes_sent"] == 0
    assert out[0]["bytes_recv"] == 0


def test_get_services_parses_systemctl_columns():
    fake_stdout = (
        "nginx.service loaded active running The nginx HTTP server\n"
        "sshd.service  loaded active running OpenBSD Secure Shell server\n"
    )
    fake_proc = MagicMock()
    fake_proc.check_output.return_value = fake_stdout
    with patch("main.subprocess.check_output", fake_proc.check_output):
        out = main.get_services()
    assert len(out) == 2
    assert out[0]["unit"] == "nginx.service"
    assert out[0]["active"] == "active"
    assert out[0]["sub"] == "running"
    assert "nginx HTTP" in out[0]["description"]


def test_get_services_skips_short_lines():
    fake_stdout = "garbage line\nnginx.service loaded active running nginx\n"
    fake_proc = MagicMock()
    fake_proc.check_output.return_value = fake_stdout
    with patch("main.subprocess.check_output", fake_proc.check_output):
        out = main.get_services()
    assert len(out) == 1
    assert out[0]["unit"] == "nginx.service"


def test_get_services_returns_error_marker_on_failure():
    with patch("main.subprocess.check_output", side_effect=FileNotFoundError("no systemctl")):
        out = main.get_services()
    assert out == [{"unit": "error", "load": "", "active": "", "sub": "", "description": "no systemctl"}]


def test_stats_aggregates_all_sections():
    fake_vm = MagicMock(total=1000, available=600, used=400, percent=40.0)
    fake_sw = MagicMock(total=500, used=100, free=400, percent=20.0)
    with patch("main.psutil.virtual_memory", return_value=fake_vm), \
         patch("main.psutil.swap_memory", return_value=fake_sw), \
         patch("main.psutil.cpu_percent", return_value=12.5), \
         patch("main.psutil.cpu_count", side_effect=[4, 8]), \
         patch("main.os.getloadavg", return_value=(0.1, 0.2, 0.3)), \
         patch("main.get_disks", return_value=[{"device": "/dev/sda1"}]), \
         patch("main.get_uptime", return_value={"days": 0, "hours": 0}), \
         patch("main.get_network", return_value=[{"interface": "lo"}]), \
         patch("main.get_services", return_value=[{"unit": "x"}]), \
         patch("main.time.time", return_value=1700000000.0):
        out = main.stats()
    assert out["timestamp"] == 1700000000.0
    assert out["cpu"]["percent"] == 12.5
    assert out["cpu"]["count"] == 4
    assert out["cpu"]["count_logical"] == 8
    assert out["ram"]["used"] == 400
    assert out["swap"]["percent"] == 20.0
    assert out["load_average"] == [0.1, 0.2, 0.3]
    assert out["disks"] == [{"device": "/dev/sda1"}]
    assert out["network"] == [{"interface": "lo"}]
    assert out["services"] == [{"unit": "x"}]


def test_index_serves_html():
    from starlette.testclient import TestClient
    client = TestClient(main.app)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "System Monitor" in resp.text
