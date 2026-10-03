# system-monitor

Single-file FastAPI dashboard for live Linux host metrics: CPU, RAM, swap,
disks, network interfaces, uptime/load, and systemd service status. Pulls
data from `psutil` and `systemctl`, serves a self-contained HTML page that
auto-refreshes every 3 seconds.

Also includes private, link-only status pages for operator-configured servers.
Each page has its own token and target list; target hosts are never returned.

## Endpoints

- `GET /` — dashboard HTML
- `GET /api/stats` — JSON snapshot
- `GET /status` — status page shell (contains no status data)
- `POST /api/status` — private status snapshot; requires the page token

## Run

```bash
pip install fastapi psutil uvicorn
python3 main.py            # or: uvicorn main:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000/`.

Configure pages and their checks with a JSON list in `STATUS_PAGES`:

```sh
STATUS_PAGES='[{"name":"My servers","token":"REPLACE_WITH_RANDOM_TOKEN","targets":[{"name":"VPS 1","host":"203.0.113.10"},{"name":"Backup","host":"backup.example.com"}]}]' \
  uvicorn main:app --host 0.0.0.0 --port 8000
```

Generate a strong URL-safe token with `python3 -c 'import secrets; print(secrets.token_urlsafe(32))'` and replace the example value. Tokens must be at least 32 characters. Add another object to `STATUS_PAGES` for each independent private page. Share a link like `https://monitor.example/status#TOKEN`; the fragment is not sent in the HTTP request, and the page submits the token in a POST body. Anyone with the full link can view that page, so keep it private; rotate access by replacing its token. The API returns names and ping results, never target IPs or hostnames. Pages poll every 30 seconds. ICMP filtering can show a server as unavailable even when its application services are healthy.

The host must have the `ping` utility installed (for example, package `iputils-ping` on Debian/Ubuntu); without it, targets appear unavailable.

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
