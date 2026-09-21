"""Один цикл: взять активные площадки из catalog, отправить показания в telemetry."""

import os

import httpx

from app.generator import sample

CATALOG_URL = os.environ.get("CATALOG_URL", "http://127.0.0.1:8081")
TELEMETRY_URL = os.environ.get("TELEMETRY_URL", "http://127.0.0.1:8082")


def active_sites() -> list[dict]:
    url = f"{CATALOG_URL.rstrip('/')}/sites"
    response = httpx.get(url, params={"status": "active"}, timeout=3.0)
    response.raise_for_status()
    return response.json().get("items") or []


def send_reading(site_id: str, metric: str, value: float, unit: str) -> None:
    url = f"{TELEMETRY_URL.rstrip('/')}/readings"
    response = httpx.post(
        url,
        json={"site_id": site_id, "metric": metric, "value": value, "unit": unit},
        timeout=3.0,
    )
    response.raise_for_status()


def run_cycle() -> dict:
    sites = active_sites()
    sent = 0
    for site in sites:
        site_id = site["id"]
        profile = site.get("metrics_profile") or ""
        for metric, value, unit in sample(profile):
            send_reading(site_id, metric, value, unit)
            sent += 1
    return {"sites": len(sites), "readings": sent}
