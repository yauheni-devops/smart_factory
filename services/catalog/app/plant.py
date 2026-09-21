"""Чтение каталога завода из data/plant.yaml."""

from functools import lru_cache
from pathlib import Path

import yaml

# services/catalog/app/plant.py → корень репозитория на 3 уровня выше
REPO_ROOT = Path(__file__).resolve().parents[3]
PLANT_PATH = REPO_ROOT / "data" / "plant.yaml"


@lru_cache(maxsize=1)
def load_plant() -> dict:
    if not PLANT_PATH.is_file():
        raise FileNotFoundError(f"Нет каталога завода: {PLANT_PATH}")
    with PLANT_PATH.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not data or "sites" not in data:
        raise ValueError("plant.yaml должен содержать ключ sites")
    return data


def sites(*, site_type: str | None = None, status: str | None = None) -> list[dict]:
    result = list(load_plant()["sites"])
    if site_type:
        result = [s for s in result if s.get("type") == site_type]
    if status:
        result = [s for s in result if s.get("status") == status]
    return result


def site_by_id(site_id: str) -> dict | None:
    for item in load_plant()["sites"]:
        if item.get("id") == site_id:
            return item
    return None


def topology() -> list[dict]:
    """КТП и список площадок, которые оно питает."""
    rows = []
    for item in sites(site_type="ktp"):
        electrical = item.get("electrical") or {}
        rows.append(
            {
                "ktp_id": item["id"],
                "name": item["name"],
                "rated_power_kva": electrical.get("rated_power_kva"),
                "feeds": electrical.get("feeds") or [],
            }
        )
    return rows
