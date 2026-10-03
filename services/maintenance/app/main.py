"""Equipment registry, planned maintenance and dashboard API."""

import calendar
import base64
import binascii
import os
import secrets
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import httpx
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from prometheus_client import Gauge
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy import desc, func, select, text
from sqlalchemy.orm import Session

load_dotenv(Path(__file__).resolve().parents[3] / ".env", override=False)

from app.db import engine, get_db
from app.models import Base, Equipment, MaintenanceEvent, MaintenanceOrder, MaintenancePlan, MeterReading

PTO_ACCESS_USERNAME = os.getenv("PTO_ACCESS_USERNAME", "pto")
SESSION_COOKIE = "pto_session"
SESSION_LIFETIME = timedelta(hours=8)
sessions: dict[str, datetime] = {}


class LoginRequest(BaseModel):
    username: str
    password: str


def valid_credentials(username: str, password: str) -> bool:
    expected_password = os.getenv("PTO_ACCESS_PASSWORD", "")
    return (
        len(expected_password) >= 6
        and secrets.compare_digest(username.encode(), PTO_ACCESS_USERNAME.encode())
        and secrets.compare_digest(password.encode(), expected_password.encode())
    )


def authenticated(request: Request) -> bool:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        expires_at = sessions.get(token)
        if expires_at and expires_at > datetime.now(timezone.utc):
            return True
        sessions.pop(token, None)

    header = request.headers.get("authorization", "")
    try:
        scheme, encoded = header.split(None, 1)
        if scheme.lower() != "basic":
            return False
        username, password = base64.b64decode(encoded, validate=True).decode("utf-8").split(":", 1)
    except (ValueError, UnicodeDecodeError, binascii.Error):
        return False
    return valid_credentials(username, password)


def home_url(request: Request, destination: str) -> str:
    """Return only a known local home page, never an arbitrary redirect target."""
    host = request.url.hostname
    if host not in {"localhost", "127.0.0.1"}:
        host = "localhost"
    port = 8080 if destination == "frontend" else 8082
    return f"{request.url.scheme}://{host}:{port}/ui"

app = FastAPI(
    title="construction-materials-maintenance",
    version="0.1.0",
    description="Реестр оборудования, планы планово-технического обслуживания и контроль наработки.",
)


@app.middleware("http")
async def protect_maintenance_data(request, call_next):
    """Require a login session or explicit Basic credentials for maintenance data."""
    path = request.url.path
    protected = path == "/ui" or path.startswith("/ui/") or path == "/api" or path.startswith("/api/")
    if not protected:
        return await call_next(request)

    if len(os.getenv("PTO_ACCESS_PASSWORD", "")) < 6:
        return JSONResponse(
            status_code=503,
            content={"detail": "Задайте PTO_ACCESS_PASSWORD (не менее 6 символов) в корневом .env"},
        )
    if not authenticated(request):
        if path == "/ui":
            return RedirectResponse(url="/login", status_code=303)
        return JSONResponse(status_code=401, content={"detail": "Требуется вход в раздел планово-технического обслуживания"})
    return await call_next(request)


@app.get("/login")
def login_page(request: Request, next: str = "pto"):
    if authenticated(request):
        target = home_url(request, next) if next in {"home", "frontend"} else "/ui"
        return RedirectResponse(url=target, status_code=303)
    return FileResponse(Path(__file__).resolve().parent / "static" / "login.html")


@app.get("/assets/login-background.webp")
def login_background():
    path = Path(__file__).resolve().parent / "static" / "assets" / "login-background.webp"
    return FileResponse(path, media_type="image/webp")


@app.post("/login")
def login(body: LoginRequest, request: Request):
    if len(os.getenv("PTO_ACCESS_PASSWORD", "")) < 6:
        raise HTTPException(503, "Задайте PTO_ACCESS_PASSWORD для раздела планово-технического обслуживания")
    if not valid_credentials(body.username, body.password):
        raise HTTPException(401, "Неверный логин или пароль")
    now = datetime.now(timezone.utc)
    for token, expires_at in list(sessions.items()):
        if expires_at <= now:
            sessions.pop(token, None)
    token = secrets.token_urlsafe(32)
    sessions[token] = now + SESSION_LIFETIME
    response = JSONResponse({"status": "ok"})
    response.set_cookie(
        SESSION_COOKIE, token, max_age=int(SESSION_LIFETIME.total_seconds()),
        httponly=True, samesite="strict", secure=request.url.scheme == "https", path="/",
    )
    return response


@app.get("/session", status_code=204)
def session_status(request: Request):
    if not authenticated(request):
        raise HTTPException(401, "Требуется вход в систему")


@app.post("/logout")
def logout(request: Request, next: str = "pto"):
    sessions.pop(request.cookies.get(SESSION_COOKIE, ""), None)
    response = (
        RedirectResponse(url=f"/login?next={next}", status_code=303)
        if next in {"home", "frontend"}
        else JSONResponse({"status": "ok"})
    )
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


equipment_assets_total = Gauge("factory_equipment_assets_total", "Registered factory equipment assets.")
maintenance_plans_by_status = Gauge(
    "factory_maintenance_plans", "Enabled maintenance plans grouped by calculated status.", ("status",)
)
maintenance_open_orders = Gauge("factory_maintenance_open_work_orders", "Open maintenance work orders.")
maintenance_plan_days_remaining = Gauge(
    "factory_maintenance_plan_days_remaining", "Calendar days until planned maintenance.", ("site_id", "plan_id")
)
maintenance_plan_hours_remaining = Gauge(
    "factory_maintenance_plan_hours_remaining", "Operating hours until planned maintenance.", ("site_id", "plan_id")
)
equipment_meter_hours = Gauge(
    "factory_equipment_meter_hours", "Latest cumulative operating-hour meter by asset.", ("equipment_id", "site_id")
)


class EquipmentCreate(BaseModel):
    id: str | None = None
    site_id: str
    name: str
    equipment_type: str
    model: str | None = None
    serial_number: str | None = None
    inventory_number: str | None = None
    rated_power_kva: float | None = Field(default=None, gt=0)
    commissioned_at: date | None = None


class PlanCreate(BaseModel):
    site_id: str
    equipment_id: str | None = None
    title: str
    scope: str = "equipment"
    interval_months: int | None = Field(default=None, ge=1)
    interval_hours: float | None = Field(default=None, gt=0)
    last_service_date: date | None = None
    last_service_meter: float | None = Field(default=None, ge=0)
    source_reference: str | None = None


class MeterReadingCreate(BaseModel):
    equipment_id: str
    value: float = Field(ge=0)
    unit: str = "h"
    meter_type: str = "operating_hours"
    source: str = "manual"
    recorded_at: datetime | None = None


class WorkOrderCreate(BaseModel):
    site_id: str
    equipment_id: str | None = None
    plan_id: str | None = None
    title: str
    due_at: date | None = None
    assignee: str | None = None


class WorkOrderComplete(BaseModel):
    work_description: str = Field(min_length=1)
    downtime_minutes: int = Field(default=0, ge=0)
    completed_meter: float | None = Field(default=None, ge=0)
    completed_at: datetime | None = None


def uid(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:12]}"


def add_months(day: date, months: int) -> date:
    month_index = day.month - 1 + months
    year = day.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def serialize_equipment(item: Equipment) -> dict:
    return {
        "id": item.id,
        "site_id": item.site_id,
        "name": item.name,
        "equipment_type": item.equipment_type,
        "model": item.model,
        "serial_number": item.serial_number,
        "inventory_number": item.inventory_number,
        "rated_power_kva": item.rated_power_kva,
        "status": item.status,
        "commissioned_at": item.commissioned_at.isoformat() if item.commissioned_at else None,
    }


def evaluate_plan(plan: MaintenancePlan, db: Session, *, within_days: int, within_hours: float) -> dict:
    equipment = db.get(Equipment, plan.equipment_id) if plan.equipment_id else None
    next_date = add_months(plan.last_service_date, plan.interval_months) if plan.last_service_date and plan.interval_months else None
    remaining_days = (next_date - date.today()).days if next_date else None
    latest_meter = None
    remaining_hours = None
    if equipment and plan.interval_hours is not None:
        latest_meter = db.scalar(
            select(MeterReading.value)
            .where(MeterReading.equipment_id == equipment.id, MeterReading.meter_type == "operating_hours")
            .order_by(desc(MeterReading.recorded_at))
            .limit(1)
        )
        if latest_meter is not None and plan.last_service_meter is not None:
            remaining_hours = plan.interval_hours - (latest_meter - plan.last_service_meter)

    missing_baseline = (plan.interval_months is not None and plan.last_service_date is None) or (
        plan.interval_hours is not None and (plan.last_service_meter is None or latest_meter is None)
    )
    overdue = (remaining_days is not None and remaining_days < 0) or (
        remaining_hours is not None and remaining_hours < 0
    )
    due_soon = (remaining_days is not None and 0 <= remaining_days <= within_days) or (
        remaining_hours is not None and 0 <= remaining_hours <= within_hours
    )
    status = "overdue" if overdue else "due_soon" if due_soon else "unknown" if missing_baseline else "ok"
    return {
        "plan_id": plan.id,
        "site_id": plan.site_id,
        "scope": plan.scope,
        "equipment_id": plan.equipment_id,
        "equipment_name": equipment.name if equipment else None,
        "title": plan.title,
        "interval_months": plan.interval_months,
        "interval_hours": plan.interval_hours,
        "last_service_date": plan.last_service_date.isoformat() if plan.last_service_date else None,
        "last_service_meter": plan.last_service_meter,
        "latest_meter": latest_meter,
        "next_service_date": next_date.isoformat() if next_date else None,
        "remaining_days": remaining_days,
        "remaining_hours": round(remaining_hours, 2) if remaining_hours is not None else None,
        "missing_baseline": missing_baseline,
        "status": status,
        "source_reference": plan.source_reference,
    }


def refresh_business_metrics(db: Session) -> None:
    equipment_assets_total.set(db.scalar(select(func.count()).select_from(Equipment)) or 0)
    plans = db.scalars(select(MaintenancePlan).where(MaintenancePlan.enabled.is_(True))).all()
    counts = {key: 0 for key in ("ok", "due_soon", "overdue", "unknown")}
    for plan in plans:
        values = evaluate_plan(plan, db, within_days=30, within_hours=100)
        counts[values["status"]] += 1
        if values["remaining_days"] is not None:
            maintenance_plan_days_remaining.labels(plan.site_id, plan.id).set(values["remaining_days"])
        if values["remaining_hours"] is not None:
            maintenance_plan_hours_remaining.labels(plan.site_id, plan.id).set(values["remaining_hours"])
    for status, count in counts.items():
        maintenance_plans_by_status.labels(status).set(count)
    maintenance_open_orders.set(
        db.scalar(
            select(func.count()).select_from(MaintenanceOrder).where(
                MaintenanceOrder.status.in_(["planned", "in_progress"])
            )
        )
        or 0
    )


@app.on_event("startup")
def initialize_database() -> None:
    Base.metadata.create_all(bind=engine)
    with Session(engine) as db:
        refresh_business_metrics(db)


@app.post("/api/bootstrap/catalog")
def bootstrap_from_catalog(db: Session = Depends(get_db)) -> dict:
    catalog_url = os.getenv("CATALOG_URL", "http://127.0.0.1:8081")
    try:
        response = httpx.get(f"{catalog_url}/maintenance-config", timeout=5)
        response.raise_for_status()
        config = response.json()
    except httpx.HTTPError as exc:
        raise HTTPException(503, "Каталог недоступен; запустите catalog и повторите импорт") from exc

    plans_created = 0
    assets_created = 0
    for site in config.get("sites", []):
        maintenance = site.get("maintenance") or {}
        interval_months = maintenance.get("interval_months")
        if not interval_months:
            continue
        plan_id = f"plan-{site['id']}-{interval_months}-months"
        plan = db.get(MaintenancePlan, plan_id)
        if plan is None:
            db.add(
                MaintenancePlan(
                    id=plan_id,
                    site_id=site["id"],
                    title="Планово-техническое обслуживание оборудования площадки",
                    scope="site",
                    interval_months=interval_months,
                    source_reference="Импортировано из каталога завода",
                )
            )
            plans_created += 1
    for asset in config.get("assets", []):
        equipment = db.get(Equipment, asset["id"])
        if equipment is None:
            equipment = Equipment(
                id=asset["id"],
                site_id=asset["site_id"],
                name=asset["name"],
                equipment_type=asset["type"],
                model=asset.get("model"),
                inventory_number=asset.get("inventory_number"),
                serial_number=asset.get("serial_number"),
                rated_power_kva=asset.get("rated_power_kva"),
            )
            db.add(equipment)
            assets_created += 1
        maintenance = asset.get("maintenance") or {}
        interval_months = maintenance.get("interval_months")
        if interval_months:
            plan_id = f"plan-{asset['id']}-{interval_months}-months"
            plan = db.get(MaintenancePlan, plan_id)
            if plan is None:
                db.add(
                    MaintenancePlan(
                        id=plan_id,
                        site_id=asset["site_id"],
                        equipment_id=asset["id"],
                        title=f"Плановое ТО: {asset['name']}",
                        scope="equipment",
                        interval_months=interval_months,
                    last_service_date=date.fromisoformat(maintenance["last_service_date"])
                    if maintenance.get("last_service_date")
                    else None,
                        source_reference="Импортировано из каталога завода",
                    )
                )
                plans_created += 1
    db.commit()
    refresh_business_metrics(db)
    return {"assets_created": assets_created, "plans_created": plans_created, "status": "imported"}


@app.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    db.execute(text("SELECT 1"))
    return {"status": "ok", "service": "maintenance", "database": "ok"}


@app.get("/api/equipment")
def list_equipment(db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(select(Equipment).order_by(Equipment.site_id, Equipment.name)).all()
    return {"items": [serialize_equipment(item) for item in rows]}


@app.post("/api/equipment", status_code=201)
def create_equipment(body: EquipmentCreate, db: Session = Depends(get_db)) -> dict:
    item = Equipment(id=body.id or uid("asset"), **body.model_dump(exclude={"id"}))
    db.add(item)
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(409, "Оборудование с таким ID уже существует") from exc
    db.refresh(item)
    refresh_business_metrics(db)
    return serialize_equipment(item)


@app.get("/api/plans")
def list_plans(
    within_days: int = Query(30, ge=0, le=365),
    within_hours: float = Query(100, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    plans = db.scalars(select(MaintenancePlan).where(MaintenancePlan.enabled.is_(True))).all()
    return {"items": [evaluate_plan(plan, db, within_days=within_days, within_hours=within_hours) for plan in plans]}


@app.post("/api/plans", status_code=201)
def create_plan(body: PlanCreate, db: Session = Depends(get_db)) -> dict:
    if body.interval_months is None and body.interval_hours is None:
        raise HTTPException(422, "Укажите интервал в месяцах и/или моточасах")
    if body.scope not in {"equipment", "site"}:
        raise HTTPException(422, "scope должен быть equipment или site")
    if body.equipment_id and db.get(Equipment, body.equipment_id) is None:
        raise HTTPException(404, "Оборудование не найдено")
    plan = MaintenancePlan(id=uid("plan"), **body.model_dump())
    db.add(plan)
    db.commit()
    db.refresh(plan)
    refresh_business_metrics(db)
    return evaluate_plan(plan, db, within_days=30, within_hours=100)


@app.post("/api/meter-readings", status_code=201)
def add_meter_reading(body: MeterReadingCreate, db: Session = Depends(get_db)) -> dict:
    if db.get(Equipment, body.equipment_id) is None:
        raise HTTPException(404, "Оборудование не найдено")
    latest = db.scalar(
        select(MeterReading.value)
        .where(MeterReading.equipment_id == body.equipment_id, MeterReading.meter_type == body.meter_type)
        .order_by(desc(MeterReading.recorded_at))
        .limit(1)
    )
    if latest is not None and body.value < latest:
        raise HTTPException(409, "Накопительное показание не может уменьшаться")
    recorded_at = body.recorded_at or datetime.now(timezone.utc)
    reading = MeterReading(id=uid("meter"), recorded_at=recorded_at, **body.model_dump(exclude={"recorded_at"}))
    db.add(reading)
    db.commit()
    if body.meter_type == "operating_hours":
        equipment = db.get(Equipment, body.equipment_id)
        equipment_meter_hours.labels(body.equipment_id, equipment.site_id).set(body.value)
    refresh_business_metrics(db)
    return {"id": reading.id, "equipment_id": reading.equipment_id, "value": reading.value, "unit": reading.unit, "recorded_at": reading.recorded_at.isoformat()}


@app.post("/api/work-orders", status_code=201)
def create_work_order(body: WorkOrderCreate, db: Session = Depends(get_db)) -> dict:
    if body.equipment_id and db.get(Equipment, body.equipment_id) is None:
        raise HTTPException(404, "Оборудование не найдено")
    if body.plan_id and db.get(MaintenancePlan, body.plan_id) is None:
        raise HTTPException(404, "План обслуживания не найден")
    order = MaintenanceOrder(id=uid("wo"), **body.model_dump())
    db.add(order)
    db.add(MaintenanceEvent(id=uid("event"), order_id=order.id, equipment_id=order.equipment_id, event_type="created", description="Создана заявка на обслуживание"))
    db.commit()
    refresh_business_metrics(db)
    return {"id": order.id, "site_id": order.site_id, "equipment_id": order.equipment_id, "plan_id": order.plan_id, "title": order.title, "status": order.status, "due_at": order.due_at.isoformat() if order.due_at else None}


@app.post("/api/work-orders/{order_id}/start")
def start_work_order(order_id: str, db: Session = Depends(get_db)) -> dict:
    order = db.get(MaintenanceOrder, order_id)
    if order is None:
        raise HTTPException(404, "Заявка не найдена")
    if order.status != "planned":
        raise HTTPException(409, "Начать можно только запланированную заявку")
    order.status = "in_progress"
    db.add(MaintenanceEvent(id=uid("event"), order_id=order.id, equipment_id=order.equipment_id, event_type="started", description="Работы начаты"))
    db.commit()
    refresh_business_metrics(db)
    return {"id": order.id, "status": order.status}


@app.get("/api/work-orders")
def list_work_orders(db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(
        select(MaintenanceOrder).where(MaintenanceOrder.status.in_(["planned", "in_progress"])).order_by(MaintenanceOrder.due_at)
    ).all()
    return {"items": [{"id": row.id, "site_id": row.site_id, "equipment_id": row.equipment_id, "title": row.title, "status": row.status, "due_at": row.due_at.isoformat() if row.due_at else None, "assignee": row.assignee} for row in rows]}


@app.get("/api/events")
def list_events(limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db)) -> dict:
    events = db.scalars(select(MaintenanceEvent).order_by(desc(MaintenanceEvent.event_at)).limit(limit)).all()
    return {"items": [{"id": event.id, "equipment_id": event.equipment_id, "order_id": event.order_id, "event_type": event.event_type, "description": event.description, "event_at": event.event_at.isoformat()} for event in events]}


@app.post("/api/work-orders/{order_id}/complete")
def complete_work_order(order_id: str, body: WorkOrderComplete, db: Session = Depends(get_db)) -> dict:
    order = db.get(MaintenanceOrder, order_id)
    if order is None:
        raise HTTPException(404, "Заявка не найдена")
    if order.status not in {"planned", "in_progress"}:
        raise HTTPException(409, "Заявка уже закрыта или отменена")
    completed_at = body.completed_at or datetime.now(timezone.utc)
    order.status = "completed"
    order.completed_at = completed_at
    order.work_description = body.work_description
    order.downtime_minutes = body.downtime_minutes
    if order.plan_id:
        plan = db.get(MaintenancePlan, order.plan_id)
        if plan:
            plan.last_service_date = completed_at.date()
            if body.completed_meter is not None:
                plan.last_service_meter = body.completed_meter
    db.add(MaintenanceEvent(id=uid("event"), order_id=order.id, equipment_id=order.equipment_id, event_type="completed", description=body.work_description, event_at=completed_at))
    db.commit()
    refresh_business_metrics(db)
    return {"id": order.id, "status": order.status, "completed_at": completed_at.isoformat(), "downtime_minutes": order.downtime_minutes}


@app.get("/api/dashboard")
def dashboard(db: Session = Depends(get_db)) -> dict:
    refresh_business_metrics(db)
    plans = db.scalars(select(MaintenancePlan).where(MaintenancePlan.enabled.is_(True))).all()
    statuses = [evaluate_plan(plan, db, within_days=30, within_hours=100) for plan in plans]
    orders = db.scalars(select(MaintenanceOrder).where(MaintenanceOrder.status.in_(["planned", "in_progress"]))).all()
    counts = {key: sum(1 for item in statuses if item["status"] == key) for key in ("ok", "due_soon", "overdue", "unknown")}
    return {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "equipment_count": db.scalar(select(func.count()).select_from(Equipment)) or 0,
        "plan_count": len(statuses),
        "counts": counts,
        "plans": statuses,
        "open_work_orders": [
            {"id": order.id, "site_id": order.site_id, "equipment_id": order.equipment_id, "title": order.title, "status": order.status, "due_at": order.due_at.isoformat() if order.due_at else None, "assignee": order.assignee}
            for order in orders
        ],
    }


@app.get("/")
def root():
    return RedirectResponse(url="/ui")


@app.get("/ui")
def dashboard_page():
    return FileResponse(Path(__file__).resolve().parent / "static" / "index.html")


Instrumentator().instrument(app).expose(app, include_in_schema=False)
