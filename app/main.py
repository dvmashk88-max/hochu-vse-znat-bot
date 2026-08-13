import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.scheduler import start_scheduler
from app.db import init_db
from app.config import ADMIN_TELEGRAM_CHAT_ID, COURSE_ALERTS_ENABLED, COURSE_CURRICULUM_PATH
from app.course.alerts import send_admin_alert, system_alert
from app.course.curriculum import load_curriculum_catalog
from app.course.readiness import readiness, startup_summary
from app.course.repository import init_course_storage
from app.database import database
from app.marketcode.config import load_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("telegram.ext").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        catalog = load_curriculum_catalog(COURSE_CURRICULUM_PATH)
        readiness.curriculum_loaded = True
    except Exception as exc:
        await send_admin_alert(system_alert(
            "curriculum_validation_failed", "startup", "curriculum не прошёл startup validation", str(exc)
        ), persistent_dedupe=False)
        raise
    try:
        init_db()
        init_course_storage()
        readiness.database_ready = True
    except Exception as exc:
        await send_admin_alert(system_alert(
            "database_error", "startup", "course database не готова", str(exc)
        ), persistent_dedupe=False)
        raise
    try:
        start_scheduler()
        readiness.scheduler_started = True
    except Exception as exc:
        await send_admin_alert(system_alert(
            "curriculum_validation_failed", "scheduler-startup",
            "course scheduler не может безопасно стартовать", str(exc),
        ), persistent_dedupe=False)
        raise
    logging.getLogger(__name__).info("\n%s", startup_summary(catalog, database, load_settings()))
    if not COURSE_ALERTS_ENABLED or not ADMIN_TELEGRAM_CHAT_ID:
        logging.getLogger(__name__).warning(
            "Course admin alerts are disabled or ADMIN_TELEGRAM_CHAT_ID is not configured"
        )
    yield
    readiness.scheduler_started = False


app = FastAPI(title="Хочу всё знать — бот", lifespan=lifespan)


@app.get("/")
async def root() -> dict:
    return {"status": "ok", "bot": "Хочу всё знать"}


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "course": readiness.public_dict()}
