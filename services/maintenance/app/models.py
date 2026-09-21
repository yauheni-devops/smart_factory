"""Database records for equipment, maintenance plans and work history."""

from datetime import date, datetime, timezone

from sqlalchemy import CheckConstraint, Date, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Equipment(Base):
    __tablename__ = "equipment"
    __table_args__ = (CheckConstraint("status in ('active', 'reserve', 'retired')"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    site_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(200))
    equipment_type: Mapped[str] = mapped_column(String(80))
    model: Mapped[str | None] = mapped_column(String(160), nullable=True)
    serial_number: Mapped[str | None] = mapped_column(String(120), nullable=True)
    inventory_number: Mapped[str | None] = mapped_column(String(120), nullable=True)
    rated_power_kva: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active")
    commissioned_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class MaintenancePlan(Base):
    __tablename__ = "maintenance_plans"
    __table_args__ = (
        CheckConstraint("interval_months is not null or interval_hours is not null"),
        CheckConstraint("scope in ('equipment', 'site')"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    site_id: Mapped[str] = mapped_column(String(64), index=True)
    equipment_id: Mapped[str | None] = mapped_column(
        ForeignKey("equipment.id", ondelete="CASCADE"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    scope: Mapped[str] = mapped_column(String(16), default="equipment")
    interval_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    interval_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_service_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_service_meter: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_reference: Mapped[str | None] = mapped_column(String(300), nullable=True)
    enabled: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class MeterReading(Base):
    __tablename__ = "meter_readings"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    equipment_id: Mapped[str] = mapped_column(ForeignKey("equipment.id", ondelete="CASCADE"), index=True)
    meter_type: Mapped[str] = mapped_column(String(40), default="operating_hours")
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(24), default="h")
    source: Mapped[str] = mapped_column(String(40), default="manual")
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class MaintenanceOrder(Base):
    __tablename__ = "maintenance_orders"
    __table_args__ = (
        CheckConstraint("status in ('planned', 'in_progress', 'completed', 'cancelled')"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    site_id: Mapped[str] = mapped_column(String(64), index=True)
    equipment_id: Mapped[str | None] = mapped_column(
        ForeignKey("equipment.id", ondelete="SET NULL"), nullable=True, index=True
    )
    plan_id: Mapped[str | None] = mapped_column(
        ForeignKey("maintenance_plans.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="planned")
    due_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    assignee: Mapped[str | None] = mapped_column(String(120), nullable=True)
    work_description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    downtime_minutes: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MaintenanceEvent(Base):
    __tablename__ = "maintenance_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    order_id: Mapped[str | None] = mapped_column(
        ForeignKey("maintenance_orders.id", ondelete="SET NULL"), nullable=True, index=True
    )
    equipment_id: Mapped[str | None] = mapped_column(
        ForeignKey("equipment.id", ondelete="SET NULL"), nullable=True, index=True
    )
    event_type: Mapped[str] = mapped_column(String(40))
    description: Mapped[str] = mapped_column(String(2000))
    event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
