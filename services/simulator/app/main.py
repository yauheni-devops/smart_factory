"""Процесс-имитатор: фон шлёт показания, HTTP только для статуса."""

import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from app.client import run_cycle

INTERVAL_SEC = float(os.environ.get("SIMULATOR_INTERVAL_SEC", "5"))

state: dict = {
    "running": False,
    "last_ok": None,
    "last_error": None,
    "last_cycle": None,
}


async def _loop() -> None:
    state["running"] = True
    while True:
        try:
            summary = await asyncio.to_thread(run_cycle)
            state["last_ok"] = datetime.now(timezone.utc).isoformat()
            state["last_error"] = None
            state["last_cycle"] = summary
        except Exception as exc:
            state["last_error"] = str(exc)
        await asyncio.sleep(INTERVAL_SEC)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    task = asyncio.create_task(_loop())
    try:
        yield
    finally:
        task.cancel()
        state["running"] = False


app = FastAPI(
    title="construction-materials-simulator",
    version="0.1.0",
    description="Имитация датчиков завода строительных материалов. Пишет только в telemetry.",
    lifespan=lifespan,
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "simulator"}


@app.get("/status")
def status() -> dict:
    return {
        "service": "simulator",
        "interval_sec": INTERVAL_SEC,
        **state,
    }


Instrumentator().instrument(app).expose(app, include_in_schema=False)
