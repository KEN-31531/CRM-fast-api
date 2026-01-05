from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.services import db_service
from app.models.schemas import CustomerResponse

router = APIRouter(prefix="/customers", tags=["顧客"])


@router.get("/", response_model=list[dict])
async def get_all_customers(db: AsyncSession = Depends(get_db)):
    """取得所有顧客及其活動參與記錄"""
    return await db_service.get_customer_activities(db)


@router.get("/list", response_model=list[CustomerResponse])
async def get_customer_list(db: AsyncSession = Depends(get_db)):
    """取得顧客列表"""
    return await db_service.get_all_customers(db)


@router.get("/{phone}")
async def get_customer_by_phone(phone: str, db: AsyncSession = Depends(get_db)):
    """根據電話查詢顧客"""
    customer = await db_service.get_customer_by_phone(db, phone)
    if not customer:
        return {"error": "顧客不存在"}
    return customer
