import os
import subprocess
import time

import psutil
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI()


def get_uptime():
    try:
        with open("/proc/uptime") as f:
            seconds = float(f.read().split()[0])
    except (OSError, IndexError, ValueError):
        # /proc may be unavailable in containers or non-Linux environments.
        seconds = max(0.0, time.time() - psutil.boot_time())
    days = int(seconds // 86400)
    hours = int((seconds % 86400) // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return {
        "total_seconds": seconds,
        "days": days,
        "hours": hours,
        "minutes": minutes,
        "seconds": secs,
    }


def get_disks():
    disks = []
    for p in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(p.mountpoint)
            disks.append(
                {
                    "device": p.device,
                    "mountpoint": p.mountpoint,
                    "fstype": p.fstype,
                    "total": usage.total,
                    "used": usage.used,
                    "free": usage.free,
                    "percent": usage.percent,
                }
            )
        except PermissionError:
            pass
    return disks


def get_network():
    addrs = psutil.net_if_addrs()
    counters = psutil.net_io_counters(pernic=True)
    result = []
    for iface, addr_list in addrs.items():
        ipv4 = next((a.address for a in addr_list if a.family.name == "AF_INET"), None)
        ipv6 = next((a.address for a in addr_list if a.family.name == "AF_INET6"), None)
        c = counters.get(iface)
        result.append(
            {
                "interface": iface,
                "ipv4": ipv4,
                "ipv6": ipv6,
                "bytes_sent": c.bytes_sent if c else 0,
                "bytes_recv": c.bytes_recv if c else 0,
            }
        )
    return result


def get_services():
    try:
        out = subprocess.check_output(
            ["systemctl", "list-units", "--type=service", "--no-pager", "--no-legend"],
            text=True,
            timeout=5,
        )
        services = []
        for line in out.strip().splitlines():
            parts = line.split()
            if len(parts) >= 4:
                services.append(
                    {
                        "unit": parts[0],
                        "load": parts[1],
                        "active": parts[2],
                        "sub": parts[3],
                        "description": " ".join(parts[4:]),
                    }
                )
        return services
    except Exception as e:  # noqa: BLE001
        return [
            {
                "unit": "error",
                "load": "",
                "active": "",
                "sub": "",
                "description": str(e),
            }
        ]


@app.get("/api/stats")
def stats():
    vm = psutil.virtual_memory()
    sw = psutil.swap_memory()
    return {
        "timestamp": time.time(),
        "cpu": {
            "percent": psutil.cpu_percent(interval=1),
            "count": psutil.cpu_count(logical=False),
            "count_logical": psutil.cpu_count(logical=True),
        },
        "ram": {
            "total": vm.total,
            "available": vm.available,
            "used": vm.used,
            "percent": vm.percent,
        },
        "swap": {
            "total": sw.total,
            "used": sw.used,
            "free": sw.free,
            "percent": sw.percent,
        },
        "disks": get_disks(),
        "uptime": get_uptime(),
        "load_average": list(os.getloadavg()),
        "network": get_network(),
        "services": get_services(),
    }


HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>System Monitor</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: #0f0f1a; color: #e0e0e0; font-family: 'Segoe UI', system-ui, sans-serif; padding: 20px; }
  h1 { color: #7eb8f7; margin-bottom: 4px; font-size: 1.6em; }
  .subtitle { color: #555; font-size: 0.85em; margin-bottom: 24px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 16px; }
  .card { background: #1a1a2e; border: 1px solid #2a2a4a; border-radius: 10px; padding: 18px; }
  .card h2 { color: #a78bfa; font-size: 0.78em; margin-bottom: 14px; text-transform: uppercase; letter-spacing: 1.5px; }
  .bar-wrap { background: #0f0f1a; border-radius: 4px; height: 10px; margin: 5px 0 10px; overflow: hidden; }
  .bar { height: 100%; border-radius: 4px; transition: width 0.6s ease; }
  .bar-cpu  { background: linear-gradient(90deg, #3b82f6, #7eb8f7); }
  .bar-ram  { background: linear-gradient(90deg, #059669, #34d399); }
  .bar-swap { background: linear-gradient(90deg, #d97706, #fbbf24); }
  .bar-disk { background: linear-gradient(90deg, #dc2626, #f87171); }
  .bar-warn { background: linear-gradient(90deg, #b45309, #fbbf24) !important; }
  .bar-crit { background: #dc2626 !important; }
  .stat-row { display: flex; justify-content: space-between; font-size: 0.87em; color: #888; margin-bottom: 5px; }
  .val { color: #fff; font-weight: 600; }
  table { width: 100%; border-collapse: collapse; font-size: 0.81em; }
  th { color: #a78bfa; text-align: left; padding: 5px 8px; border-bottom: 1px solid #2a2a4a; font-weight: 500; }
  td { padding: 5px 8px; color: #ccc; border-bottom: 1px solid #1e1e35; }
  tr:hover td { background: #22224a; }
  .badge { display: inline-block; padding: 1px 8px; border-radius: 10px; font-size: 0.76em; font-weight: 700; }
  .running { background: #052e16; color: #34d399; }
  .failed  { background: #3b0000; color: #f87171; }
  .other   { background: #1e1e35; color: #888; }
  .full { grid-column: 1 / -1; }
  #ts { color: #444; font-size: 0.78em; margin-top: 18px; text-align: right; }
</style>
</head>
<body>
<h1>⚡ System Monitor</h1>
<div class="subtitle">Live metrics · auto-refresh every 3s</div>
<div class="grid">
  <div class="card"><h2>CPU</h2><div id="cpu">Loading…</div></div>
  <div class="card"><h2>Memory</h2><div id="ram">Loading…</div></div>
  <div class="card"><h2>Swap</h2><div id="swap">Loading…</div></div>
  <div class="card"><h2>Uptime &amp; Load</h2><div id="uptime">Loading…</div></div>
  <div class="card full"><h2>Disks</h2><div id="disks">Loading…</div></div>
  <div class="card full"><h2>Network</h2><div id="net">Loading…</div></div>
  <div class="card full"><h2>Systemd Services</h2><div id="svc">Loading…</div></div>
</div>
<div id="ts"></div>
<script>
function fmt(b) {
  if (b < 1024) return b + ' B';
  if (b < 1048576) return (b/1024).toFixed(1) + ' KB';
  if (b < 1073741824) return (b/1048576).toFixed(1) + ' MB';
  return (b/1073741824).toFixed(2) + ' GB';
}
function bar(pct, cls) {
  const extra = pct > 85 ? ' bar-crit' : pct > 65 ? ' bar-warn' : '';
  return `<div class="bar-wrap"><div class="bar ${cls}${extra}" style="width:${Math.min(pct,100)}%"></div></div>`;
}
function badge(sub) {
  const c = sub==='running' ? 'running' : sub==='failed' ? 'failed' : 'other';
  return `<span class="badge ${c}">${sub}</span>`;
}
async function refresh() {
  try {
    const d = await fetch('/api/stats').then(r => r.json());

    document.getElementById('cpu').innerHTML =
      `<div class="stat-row"><span>Usage</span><span class="val">${d.cpu.percent}%</span></div>` +
      bar(d.cpu.percent, 'bar-cpu') +
      `<div class="stat-row"><span>Cores (physical / logical)</span><span class="val">${d.cpu.count} / ${d.cpu.count_logical}</span></div>`;

    const r = d.ram;
    document.getElementById('ram').innerHTML =
      `<div class="stat-row"><span>Used</span><span class="val">${fmt(r.used)} / ${fmt(r.total)}</span></div>` +
      bar(r.percent, 'bar-ram') +
      `<div class="stat-row"><span>Available</span><span class="val">${fmt(r.available)}</span></div>`;

    const sw = d.swap;
    document.getElementById('swap').innerHTML = sw.total === 0
      ? '<div class="stat-row"><span>No swap configured</span></div>'
      : `<div class="stat-row"><span>Used</span><span class="val">${fmt(sw.used)} / ${fmt(sw.total)}</span></div>` +
        bar(sw.percent, 'bar-swap') +
        `<div class="stat-row"><span>Free</span><span class="val">${fmt(sw.free)}</span></div>`;

    const u = d.uptime;
    document.getElementById('uptime').innerHTML =
      `<div class="stat-row"><span>Uptime</span><span class="val">${u.days}d ${u.hours}h ${u.minutes}m</span></div>` +
      `<div class="stat-row"><span>Load 1 / 5 / 15 min</span><span class="val">${d.load_average.map(x=>x.toFixed(2)).join(' / ')}</span></div>`;

    document.getElementById('disks').innerHTML = '<table><tr><th>Device</th><th>Mount</th><th>FS</th><th>Total</th><th>Used</th><th>Free</th><th>Usage</th></tr>' +
      d.disks.map(k => `<tr><td>${k.device}</td><td>${k.mountpoint}</td><td>${k.fstype}</td><td>${fmt(k.total)}</td><td>${fmt(k.used)}</td><td>${fmt(k.free)}</td><td><div class="bar-wrap" style="width:90px;display:inline-block;vertical-align:middle"><div class="bar bar-disk" style="width:${k.percent}%"></div></div> ${k.percent}%</td></tr>`).join('') + '</table>';

    document.getElementById('net').innerHTML = '<table><tr><th>Interface</th><th>IPv4</th><th>IPv6</th><th>↓ Received</th><th>↑ Sent</th></tr>' +
      d.network.map(n => `<tr><td>${n.interface}</td><td>${n.ipv4||'—'}</td><td style="font-size:0.8em;color:#555">${(n.ipv6||'').substring(0,28)||'—'}</td><td>${fmt(n.bytes_recv)}</td><td>${fmt(n.bytes_sent)}</td></tr>`).join('') + '</table>';

    document.getElementById('svc').innerHTML = '<table><tr><th>Unit</th><th>Status</th><th>Active</th><th>Description</th></tr>' +
      d.services.map(s => `<tr><td>${s.unit}</td><td>${badge(s.sub)}</td><td>${s.active}</td><td style="color:#666">${s.description}</td></tr>`).join('') + '</table>';

    document.getElementById('ts').textContent = 'Last updated: ' + new Date().toLocaleTimeString();
  } catch(e) {
    document.getElementById('ts').textContent = 'Fetch error: ' + e.message;
  }
}
refresh();
setInterval(refresh, 3000);
</script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
def index():
    return HTML
