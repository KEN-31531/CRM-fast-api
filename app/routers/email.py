from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.db_models import Customer
from app.services.email_service import email_service

router = APIRouter(prefix="/email", tags=["Email"])


class SendGreetingRequest(BaseModel):
    customer_ids: list[int]
    festival: str
    custom_message: str = ""


class SendSingleEmailRequest(BaseModel):
    to: str
    subject: str
    body_html: str


@router.get("/festivals")
def get_festivals():
    """取得可用的節慶列表"""
    return email_service.get_available_festivals()


@router.post("/send-greeting")
async def send_festival_greeting(
    request: SendGreetingRequest,
    db: AsyncSession = Depends(get_db)
):
    """發送節慶祝賀給指定顧客"""
    results = []

    for customer_id in request.customer_ids:
        # 取得顧客資料
        result = await db.execute(
            select(Customer).where(Customer.id == customer_id)
        )
        customer = result.scalar_one_or_none()

        if not customer:
            results.append({
                "customer_id": customer_id,
                "success": False,
                "error": "顧客不存在"
            })
            continue

        if not customer.email:
            results.append({
                "customer_id": customer_id,
                "name": customer.name,
                "success": False,
                "error": "顧客沒有 Email"
            })
            continue

        # 發送祝賀信
        send_result = await email_service.send_festival_greeting(
            to=customer.email,
            customer_name=customer.name,
            festival=request.festival,
            custom_message=request.custom_message
        )

        results.append({
            "customer_id": customer_id,
            "name": customer.name,
            "email": customer.email,
            **send_result
        })

    success_count = sum(1 for r in results if r.get("success"))
    return {
        "total": len(request.customer_ids),
        "success_count": success_count,
        "failed_count": len(request.customer_ids) - success_count,
        "results": results
    }


@router.post("/send-greeting-all")
async def send_festival_greeting_to_all(
    festival: str,
    custom_message: str = "",
    db: AsyncSession = Depends(get_db)
):
    """發送節慶祝賀給所有顧客"""
    result = await db.execute(select(Customer).where(Customer.email.isnot(None)))
    customers = result.scalars().all()

    customer_ids = [c.id for c in customers if c.email]

    if not customer_ids:
        return {"message": "沒有顧客有 Email 地址"}

    request = SendGreetingRequest(
        customer_ids=customer_ids,
        festival=festival,
        custom_message=custom_message
    )

    return await send_festival_greeting(request, db)


@router.get("/preview/{festival}")
def preview_festival_template(festival: str, customer_name: str = "顧客"):
    """預覽節慶 Email 模板"""
    template = email_service.get_festival_template(festival, customer_name)
    return template


@router.post("/send")
async def send_custom_email(request: SendSingleEmailRequest):
    """發送自訂 Email"""
    result = await email_service.send_email(
        to=request.to,
        subject=request.subject,
        body_html=request.body_html
    )
    return result
