import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.scheduler import start_scheduler
from app.db import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    start_scheduler()
    yield


app = FastAPI(title="Хочу всё знать — бот", lifespan=lifespan)


@app.get("/")
async def root() -> dict:
    return {"status": "ok", "bot": "Хочу всё знать"}


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
