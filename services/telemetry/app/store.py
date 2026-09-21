"""Показания в памяти процесса. Не база данных: после рестарта список пустой."""

from collections import deque

_MAX = 2000
_readings: deque[dict] = deque(maxlen=_MAX)


def add(reading: dict) -> dict:
    _readings.append(reading)
    return reading


def list_all(*, site_id: str | None = None, limit: int = 50) -> list[dict]:
    items = list(_readings)
    if site_id:
        items = [r for r in items if r["site_id"] == site_id]
    return items[-limit:]


def latest() -> list[dict]:
    """Последнее показание для каждой пары site_id + metric."""
    by_key: dict[tuple[str, str], dict] = {}
    for item in _readings:
        by_key[(item["site_id"], item["metric"])] = item
    return list(by_key.values())
