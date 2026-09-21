"""Заявки на выпуск продукции и контроль план/факт."""

from datetime import date, datetime, timezone
from uuid import uuid4

import httpx
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from prometheus_client import Gauge
from prometheus_fastapi_instrumentator import Instrumentator

CATALOG_URL = "http://127.0.0.1:8081"
STATUSES = {"created", "in_progress", "review", "closed", "rejected"}
TRANSITIONS = {
    "created": {"in_progress", "rejected"},
    "in_progress": {"review", "rejected"},
    "review": {"closed", "in_progress", "rejected"},
    "closed": set(),
    "rejected": set(),
}

orders: dict[str, dict] = {}
production_orders_by_status = Gauge(
    "factory_production_orders", "In-memory production orders grouped by status.", ("status",)
)

app = FastAPI(
    title="construction-materials-production",
    version="0.1.0",
    description="Заявки на выпуск сухих смесей и эмульсии.",
)


class OrderCreate(BaseModel):
    product_id: str
    qty_planned: float = Field(gt=0)
    due_date: date | None = None


class OrderProgress(BaseModel):
    qty_actual: float = Field(ge=0)


class StatusChange(BaseModel):
    status: str


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def refresh_order_metrics() -> None:
    for status in STATUSES:
        production_orders_by_status.labels(status).set(
            sum(1 for order in orders.values() if order["status"] == status)
        )


def catalog_routes() -> list[dict]:
    try:
        response = httpx.get(f"{CATALOG_URL}/routes", timeout=3)
        response.raise_for_status()
        return response.json().get("products", [])
    except httpx.HTTPError as exc:
        raise HTTPException(503, "Каталог недоступен") from exc


def get_product(product_id: str) -> dict:
    product = next((p for p in catalog_routes() if p.get("id") == product_id), None)
    if product is None:
        raise HTTPException(400, f"Неизвестный продукт: {product_id}")
    return product


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "production", "orders": len(orders)}


@app.get("/routes")
def routes() -> dict:
    return {"items": catalog_routes()}


@app.post("/orders", status_code=201)
def create_order(body: OrderCreate) -> dict:
    product = get_product(body.product_id)
    order = {
        "id": f"ord-{uuid4().hex[:8]}",
        "product_id": body.product_id,
        "product_name": product.get("name"),
        "route": product.get("route", []),
        "qty_planned": body.qty_planned,
        "qty_actual": 0,
        "status": "created",
        "due_date": body.due_date.isoformat() if body.due_date else None,
        "created_at": now(),
        "updated_at": now(),
    }
    orders[order["id"]] = order
    refresh_order_metrics()
    return order


@app.get("/orders")
def list_orders(status: str | None = Query(None)) -> dict:
    if status is not None and status not in STATUSES:
        raise HTTPException(400, f"Неизвестный статус: {status}")
    items = list(orders.values())
    if status:
        items = [item for item in items if item["status"] == status]
    return {"items": items}


@app.get("/orders/{order_id}")
def get_order(order_id: str) -> dict:
    order = orders.get(order_id)
    if order is None:
        raise HTTPException(404, "Заявка не найдена")
    return order


@app.patch("/orders/{order_id}/progress")
def update_progress(order_id: str, body: OrderProgress) -> dict:
    order = get_order(order_id)
    if order["status"] in {"closed", "rejected"}:
        raise HTTPException(409, "Завершённую заявку нельзя изменить")
    if body.qty_actual > order["qty_planned"]:
        raise HTTPException(400, "Факт не может быть больше плана")
    order["qty_actual"] = body.qty_actual
    order["updated_at"] = now()
    refresh_order_metrics()
    return order


@app.patch("/orders/{order_id}/status")
def change_status(order_id: str, body: StatusChange) -> dict:
    order = get_order(order_id)
    if body.status not in STATUSES:
        raise HTTPException(400, f"Неизвестный статус: {body.status}")
    if body.status not in TRANSITIONS[order["status"]]:
        raise HTTPException(
            409,
            f"Переход {order['status']} → {body.status} запрещён",
        )
    order["status"] = body.status
    order["updated_at"] = now()
    refresh_order_metrics()
    return order


Instrumentator().instrument(app).expose(app, include_in_schema=False)
