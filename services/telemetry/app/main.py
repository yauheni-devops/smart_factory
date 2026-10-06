"""HTTP API показаний.

Свой порт (8082), свой процесс. Площадки не дублируем: спрашиваем catalog.
"""

from datetime import datetime, timezone
import os

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
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
MAINTENANCE_AUTH_URL = os.environ.get("MAINTENANCE_AUTH_URL", "http://127.0.0.1:8086").rstrip("/")
AUTH_COOKIE = "pto_session"
PROTECTED_PAGES = {"/ui", "/monitoring", "/production", "/alerts", "/documents", "/reports"}


@app.middleware("http")
async def protect_visitor_pages(request: Request, call_next):
    path = request.url.path
    protected = request.method in {"GET", "HEAD"} and (
        path in PROTECTED_PAGES or path.startswith("/ui/")
        or path.startswith("/assets/")
        or path.startswith("/equipment-documents/")
        or path == "/readings" or path.startswith("/readings/")
    )
    if not protected:
        return await call_next(request)

    cookie = request.cookies.get(AUTH_COOKIE)
    authenticated = False
    if cookie:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                auth_response = await client.get(
                    f"{MAINTENANCE_AUTH_URL}/session",
                    headers={"Cookie": f"{AUTH_COOKIE}={cookie}"},
                )
            authenticated = auth_response.status_code == 204
        except httpx.HTTPError:
            return JSONResponse(status_code=503, content={"detail": "Сервис входа недоступен"})

    if not authenticated:
        if path in PROTECTED_PAGES:
            host = request.url.hostname
            if host not in {"localhost", "127.0.0.1"}:
                host = "localhost"
            return RedirectResponse(
                url=f"{request.url.scheme}://{host}:8086/login?next=home",
                status_code=303,
            )
        return JSONResponse(status_code=401, content={"detail": "Требуется вход в систему"})

    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response


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
DOCUMENTS_PAGE = STATIC_DIR / "documents.html"
EQUIPMENT_DOCUMENTS_DIR = Path(__file__).resolve().parents[3] / "data" / "equipment-documents"
EQUIPMENT_DOCUMENT_FILES = frozenset({
    "kinco-fv100-user-manual-en.pdf",
    "abb-acs310-user-manual-ru.pdf",
    "abb-levit-sockets-passport-ru.pdf",
})
REPORTS_PAGE = STATIC_DIR / "reports.html"
SECTIONS_CSS = STATIC_DIR / "assets" / "sections.css"
HERO_IMAGE = STATIC_DIR / "assets" / "factory-hero.png"
HORSE_IMAGE = STATIC_DIR / "assets" / "cemezit-horse.webp"
BRAND_LOGO = STATIC_DIR / "assets" / "specprofstroy-logo.png"
CEMEZIT_LOGO = STATIC_DIR / "assets" / "cemezit-logo.png"
MONITORING_BACKGROUND = STATIC_DIR / "assets" / "monitoring-background.jpg"


@app.get("/")
def root():
    return RedirectResponse(url="/ui")


@app.get("/ui")
def ui_page():
    return FileResponse(LANDING_FILE)


@app.get("/assets/factory-hero.png")
def hero_image():
    return FileResponse(HERO_IMAGE, media_type="image/png")


@app.get("/assets/specprofstroy-logo.png")
def brand_logo():
    return FileResponse(BRAND_LOGO, media_type="image/png")


@app.get("/assets/cemezit-logo.png")
def cemezit_logo():
    return FileResponse(CEMEZIT_LOGO, media_type="image/png")


@app.get("/assets/cemezit-horse.webp")
def horse_image():
    return FileResponse(HORSE_IMAGE, media_type="image/webp")


@app.get("/assets/monitoring-background.jpg")
def monitoring_background():
    return FileResponse(MONITORING_BACKGROUND, media_type="image/jpeg")


@app.get("/monitoring")
def monitoring_page():
    return FileResponse(MONITORING_FILE)


@app.get("/production")
def production_page():
    return FileResponse(PRODUCTION_PAGE)


@app.get("/alerts")
def alerts_page():
    return FileResponse(ALERTS_PAGE)


@app.get("/documents")
def documents_page():
    return FileResponse(DOCUMENTS_PAGE)


@app.api_route("/equipment-documents/{filename}", methods=["GET", "HEAD"])
def equipment_document(filename: str, download: bool = False):
    path = EQUIPMENT_DOCUMENTS_DIR / filename
    if filename not in EQUIPMENT_DOCUMENT_FILES or not path.is_file():
        raise HTTPException(status_code=404, detail="Документ не найден")
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=filename,
        content_disposition_type="attachment" if download else "inline",
        headers={"Cache-Control": "private, no-store"},
    )


@app.get("/reports")
def reports_page():
    return FileResponse(REPORTS_PAGE)


@app.get("/assets/sections.css")
def sections_stylesheet():
    return FileResponse(SECTIONS_CSS, media_type="text/css")


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
