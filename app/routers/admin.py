from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db, init_db
from app.services import db_service

router = APIRouter(prefix="/admin", tags=["管理"])


@router.post("/init-db")
async def initialize_database():
    """初始化資料庫 (建立資料表)"""
    await init_db()
    return {"message": "資料庫初始化成功"}


@router.post("/import-csv")
async def import_csv_data(db: AsyncSession = Depends(get_db)):
    """從 CSV 檔案匯入資料"""
    return await db_service.import_csv_data(db)
