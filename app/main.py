from contextlib import asynccontextmanager
from pathlib import Path
import logging
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from app.routers import customers_router, analysis_router, admin_router, email_router
from app.routers.campaigns import router as campaigns_router
from app.routers.tracking import router as tracking_router
from app.routers.schedules import router as schedules_router
from app.database import init_db
from app.services.scheduler_service import scheduler_service

BASE_DIR = Path(__file__).parent

# 設定日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 啟動時
    await init_db()

    # 初始化並啟動排程器
    scheduler_service.init_scheduler()
    scheduler_service.start()
    logger.info("CRM 系統啟動完成")

    yield

    # 關閉時
    scheduler_service.shutdown()
    logger.info("CRM 系統已關閉")


app = FastAPI(
    title="CRM 系統",
    description="顧客關係管理系統 - 追蹤顧客活動參與及課程購買",
    version="1.0.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

app.include_router(customers_router)
app.include_router(analysis_router)
app.include_router(admin_router)
app.include_router(email_router)
app.include_router(campaigns_router)
app.include_router(tracking_router)
app.include_router(schedules_router)


@app.get("/", response_class=HTMLResponse)
async def root():
    html_file = BASE_DIR / "templates" / "index.html"
    return html_file.read_text(encoding="utf-8")
