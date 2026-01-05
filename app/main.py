from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from app.routers import customers_router, analysis_router, admin_router
from app.database import init_db

BASE_DIR = Path(__file__).parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


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


@app.get("/", response_class=HTMLResponse)
async def root():
    html_file = BASE_DIR / "templates" / "index.html"
    return html_file.read_text(encoding="utf-8")
