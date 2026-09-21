"""HTTP API показаний.

Свой порт (8082), свой процесс. Площадки не дублируем: спрашиваем catalog.
"""

from datetime import datetime, timezone
import os

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, RedirectResponse
import httpx
from pydantic import BaseModel
from prometheus_client import Gauge
from prometheus_fastapi_instrumentator import Instrumentator

from app.catalog_client import CatalogError, get_site, list_sites
from app import store

app = FastAPI(
    title="construction-materials-telemetry",
    version="0.1.0",
    description="Показания датчиков завода строительных материалов.",
)
sensor_latest_value = Gauge(
    "factory_sensor_latest_value",
    "Latest received sensor value by factory site and metric.",
    ("site_id", "metric", "unit"),
)
PRODUCTION_URL = os.environ.get("PRODUCTION_URL", "http://127.0.0.1:8083").rstrip("/")


class ReadingIn(BaseModel):
    site_id: str
    metric: str
    value: float
    unit: str | None = None
    ts: datetime | None = None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "telemetry"}


@app.post("/readings", status_code=201)
def create_reading(body: ReadingIn) -> dict:
    try:
        site = get_site(body.site_id)
    except CatalogError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    if site.get("status") == "reserved":
        raise HTTPException(
            status_code=409,
            detail=f"Площадка {body.site_id} в резерве, показания не принимаем",
        )

    reading = {
        "site_id": body.site_id,
        "metric": body.metric,
        "value": body.value,
        "unit": body.unit,
        "ts": (body.ts or _utc_now()).isoformat(),
    }
    store.add(reading)
    sensor_latest_value.labels(body.site_id, body.metric, body.unit or "").set(body.value)
    return reading


@app.get("/readings")
def list_readings(site_id: str | None = None, limit: int = Query(50, ge=1, le=500)) -> dict:
    return {"items": store.list_all(site_id=site_id, limit=limit)}


@app.get("/readings/latest")
def latest_readings() -> dict:
    return {"items": store.latest()}


STATIC_DIR = Path(__file__).resolve().parent / "static"
LANDING_FILE = STATIC_DIR / "landing.html"
MONITORING_FILE = STATIC_DIR / "index.html"
PRODUCTION_PAGE = STATIC_DIR / "production.html"
ALERTS_PAGE = STATIC_DIR / "alerts.html"


@app.get("/")
def root():
    return RedirectResponse(url="/ui")


@app.get("/ui")
def ui_page():
    return FileResponse(LANDING_FILE)


@app.get("/monitoring")
def monitoring_page():
    return FileResponse(MONITORING_FILE)


@app.get("/production")
def production_page():
    return FileResponse(PRODUCTION_PAGE)


@app.get("/alerts")
def alerts_page():
    return FileResponse(ALERTS_PAGE)


@app.get("/ui/scheme")
def ui_scheme():
    png = STATIC_DIR / "scheme.png"
    jpg = STATIC_DIR / "scheme.jpg"
    path = png if png.is_file() else jpg
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Нет файла схемы scheme.png/jpg")
    media = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    return FileResponse(path, media_type=media)



@app.get("/ui/data")
def ui_data() -> dict:
    by_site: dict[str, list[dict]] = {}
    for item in store.latest():
        by_site.setdefault(item["site_id"], []).append(
            {
                "metric": item["metric"],
                "value": item["value"],
                "unit": item.get("unit"),
                "ts": item.get("ts"),
            }
        )

    try:
        sites = list_sites()
    except CatalogError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    return {
        "updated": _utc_now().isoformat(),
        "sites": [
            {
                "id": site["id"],
                "name": site.get("name") or site["id"],
                "type": site.get("type"),
                "status": site.get("status"),
                "metrics": sorted(
                    by_site.get(site["id"], []),
                    key=lambda row: row["metric"],
                ),
            }
            for site in sites
        ],
    }


@app.get("/ui/production")
def ui_production() -> dict:
    """Сводка активных заявок для стартового экрана руководителя."""
    try:
        response = httpx.get(f"{PRODUCTION_URL}/orders", timeout=2.0)
        response.raise_for_status()
        orders = response.json().get("items") or []
    except (httpx.HTTPError, ValueError):
        return {"available": False, "active_orders": 0, "planned": None, "actual": None}

    active = [order for order in orders if order.get("status") in {"created", "in_progress", "review"}]
    if not active:
        return {"available": True, "active_orders": 0, "planned": None, "actual": None, "products": []}

    planned = sum(float(order.get("qty_planned") or 0) for order in active)
    actual = sum(float(order.get("qty_actual") or 0) for order in active)
    products: dict[str, dict] = {}
    for order in active:
        product_id = order.get("product_id") or "unknown"
        item = products.setdefault(product_id, {
            "product_id": product_id,
            "product_name": order.get("product_name") or product_id,
            "orders": 0,
            "planned": 0.0,
            "actual": 0.0,
        })
        item["orders"] += 1
        item["planned"] += float(order.get("qty_planned") or 0)
        item["actual"] += float(order.get("qty_actual") or 0)
    return {
        "available": True,
        "active_orders": len(active),
        "planned": round(planned, 2),
        "actual": round(actual, 2),
        "completion_percent": round(actual / planned * 100, 1) if planned else 0,
        "products": [
            {**item, "planned": round(item["planned"], 2), "actual": round(item["actual"], 2)}
            for item in products.values()
        ],
    }


Instrumentator().instrument(app).expose(app, include_in_schema=False)
