"""Verify the running homework stack through Loki and Grafana HTTP APIs."""

import base64
import json
import os
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


GRAFANA = os.getenv("GRAFANA_URL", "http://localhost:3000").rstrip("/")
LOKI = os.getenv("LOKI_URL", "http://localhost:3100").rstrip("/")
token = base64.b64encode(
    f"{os.getenv('GRAFANA_ADMIN_USER', 'admin')}:{os.getenv('GRAFANA_ADMIN_PASSWORD', 'admin')}".encode()
).decode()


def get_json(url, data=None):
    headers = {"Content-Type": "application/json"}
    if url.startswith(GRAFANA + "/"):
        headers["Authorization"] = "Basic " + token
    req = Request(url, headers=headers, data=None if data is None else json.dumps(data).encode())
    with urlopen(req, timeout=30) as response:
        return json.load(response)


def main():
    marker = "Проверка доставки UTF-8 " + uuid.uuid4().hex
    sender = "from loki_client import send_log_to_loki; send_log_to_loki(" + repr(marker) + ", 'acceptance', 'INFO')"
    subprocess.run([
        "docker", "compose", "-f", "docker-compose.yml", "-f", "compose.app.yaml",
        "exec", "-T", "test-app", "python", "-c", sender,
    ], check=True, stdin=subprocess.DEVNULL)
    health = get_json(GRAFANA + "/api/health")
    assert health["database"] == "ok", health
    with urlopen(LOKI + "/ready", timeout=10) as response:
        assert response.status == 200
    source = get_json(GRAFANA + "/api/datasources/uid/loki")
    assert source["url"] == "http://loki:3100", source
    source_health = get_json(GRAFANA + "/api/datasources/uid/loki/health")
    assert source_health["status"] == "OK", source_health

    board = get_json(GRAFANA + "/api/dashboards/uid/my-app-logs")
    assert board["dashboard"]["title"] == "Логи приложения — Loki + Grafana", "Dashboard title encoding is incorrect"
    panels = board["dashboard"]["panels"]
    assert len(panels) == 2 and {p["type"] for p in panels} == {"table", "piechart"}
    assert board["dashboard"]["refresh"] == "5s"
    assert "$__range" in panels[1]["targets"][0]["expr"]
    now_ms = int(time.time() * 1000)
    range_query = {"query": '{app="my_app"}', "limit": 1000, "direction": "backward",
                   "start": str((now_ms - 900000) * 1000000), "end": str(now_ms * 1000000)}
    logs = get_json(LOKI + "/loki/api/v1/query_range?" + urlencode(range_query))
    streams = logs["data"]["result"]
    count = sum(len(stream["values"]) for stream in streams)
    assert count > 0, "No application logs received"
    levels = sorted({stream["stream"]["level"] for stream in streams})
    assert {"INFO", "DEBUG", "WARNING", "ERROR"} <= set(levels), levels
    messages = [value[1] for stream in streams for value in stream["values"]]
    assert marker in messages, "The log sent by send_log_to_loki was not received intact"

    # Use the saved panel queries through Grafana's own data source proxy.
    frames = {}
    for panel in panels:
        query = dict(panel["targets"][0])
        query["expr"] = query["expr"].replace("$__range", "15m")
        query.update(intervalMs=1000, maxDataPoints=1000)
        result = get_json(GRAFANA + "/api/ds/query", {
            "from": str(now_ms - 900000), "to": str(now_ms), "queries": [query]
        })["results"]["A"]
        assert not result.get("error"), result
        frame_list = result.get("frames", [])
        assert frame_list, f"No frames for panel {panel['type']}"
        rows = sum(len(frame.get("data", {}).get("values", [[]])[0]) for frame in frame_list)
        assert rows > 0, f"Empty panel {panel['type']}"
        frames[panel["type"]] = {"frames": len(frame_list), "rows": rows}

    report = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "grafana_version": health["version"],
        "loki_ready": True,
        "datasource_url": source["url"],
        "datasource_health": source_health,
        "dashboard_uid": board["dashboard"]["uid"],
        "dashboard_panels": [p["type"] for p in panels],
        "dashboard_refresh": "5s",
        "log_count_last_15_minutes": count,
        "levels": levels,
        "sender_roundtrip_utf8": True,
        "grafana_panel_data": frames,
        "status": "passed",
    }
    Path("evidence").mkdir(exist_ok=True)
    Path("evidence/verification.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
