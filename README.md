# system-monitor

Single-file FastAPI dashboard for live Linux host metrics: CPU, RAM, swap,
disks, network interfaces, uptime/load, and systemd service status. Pulls
data from `psutil` and `systemctl`, serves a self-contained HTML page that
auto-refreshes every 3 seconds.

## Endpoints

- `GET /` — dashboard HTML
- `GET /api/stats` — JSON snapshot

## Run

```bash
pip install fastapi psutil uvicorn
python3 main.py            # or: uvicorn main:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000/`.

## Test

```bash
python3 -m pytest tests/ -q
```

Tests patch `psutil`, `subprocess.check_output`, `builtins.open`, and
`os.getloadavg` so the suite runs without touching real host state. The
`/api/stats` aggregator is exercised end-to-end with mocks; the HTML page is
served through `fastapi.testclient.TestClient`.

## Layout

```
main.py            — FastAPI app + pure metric helpers
tests/test_metrics.py — 11 unit/integration tests
```

## Helpers (importable from `main`)

- `get_uptime()` — reads `/proc/uptime`, returns `{days, hours, minutes, seconds, total_seconds}`
- `get_disks()` — `psutil.disk_partitions` + `disk_usage`, skips `PermissionError`
- `get_network()` — per-interface IPv4/IPv6 + io counters, zeros when missing
- `get_services()` — `systemctl list-units` parser; returns an error marker if `systemctl` is absent
- `stats()` — `/api/stats` aggregator
