"""Direct HTTP sender following the lesson's streams / stream / values format."""

import os
import time

import requests


def send_log_to_loki(
    message: str,
    job: str = "crypto-backend",
    level: str = "INFO",
    *,
    app: str | None = None,
    loki_url: str | None = None,
    timeout: float = 5.0,
) -> None:
    """POST one log entry; raise on HTTP/network errors instead of losing it silently.

    LOKI_URL defaults to localhost for a host process. Inside Compose, set it
    to http://loki:3100. The timestamp must be a STRING of nanoseconds.
    """
    if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ValueError(f"Unsupported log level: {level}")
    labels = {
        "app": app or os.getenv("APP_NAME", "my_app"),
        "job": job,
        "level": level,
        "service": "crypto-backend",
    }
    payload = {"streams": [{"stream": labels, "values": [[str(time.time_ns()), message]]}]}
    endpoint = (loki_url or os.getenv("LOKI_URL", "http://localhost:3100")).rstrip("/")
    with requests.post(endpoint + "/loki/api/v1/push", json=payload, timeout=timeout) as response:
        if response.status_code != 204:
            raise RuntimeError(f"Loki push failed ({response.status_code}): {response.text[:2048]}")

