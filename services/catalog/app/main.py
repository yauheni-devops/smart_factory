"""HTTP API каталога завода.

Зачем этот файл: превратить plant.yaml в ответы по HTTP.
Клиент (браузер, curl, другой сервис) спрашивает по URL, процесс слушает порт.
"""

from fastapi import FastAPI, HTTPException
from prometheus_fastapi_instrumentator import Instrumentator

from app.plant import load_plant, site_by_id, sites, topology

app = FastAPI(
    title="construction-materials-catalog",
    version="0.1.0",
    description="Источник правды: площадки, КТП, маршруты выпуска.",
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "catalog"}


@app.get("/sites")
def list_sites(type: str | None = None, status: str | None = None) -> dict:
    return {"items": sites(site_type=type, status=status)}


@app.get("/sites/{site_id}")
def get_site(site_id: str) -> dict:
    item = site_by_id(site_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"Нет площадки {site_id}")
    return item


@app.get("/ktp")
def list_ktp() -> dict:
    return {"items": sites(site_type="ktp")}


@app.get("/topology")
def get_topology() -> dict:
    return {"items": topology()}


@app.get("/routes")
def get_routes() -> dict:
    production = load_plant().get("production") or {}
    return {
        "products": production.get("products") or [],
        "order_statuses": production.get("order_statuses") or [],
    }


@app.get("/maintenance-config")
def maintenance_config() -> dict:
    """Equipment and maintenance defaults used to seed the maintenance service."""
    plant = load_plant()
    return {
        "sites": [
            {"id": site["id"], "name": site["name"], "maintenance": site.get("maintenance")}
            for site in plant.get("sites", [])
            if site.get("maintenance")
        ],
        "assets": plant.get("assets") or [],
    }


Instrumentator().instrument(app).expose(app, include_in_schema=False)
