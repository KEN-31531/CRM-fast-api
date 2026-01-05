from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from pydantic import BaseModel
from typing import Optional
from datetime import date
from app.database import get_db
from app.services import db_service
from app.models.schemas import CustomerResponse
from app.models.db_models import Customer, ActivityParticipation, Course
from datetime import datetime

router = APIRouter(prefix="/customers", tags=["顧客"])


class CustomerCreate(BaseModel):
    name: str
    phone: str
    email: Optional[str] = ""
    birthday: Optional[date] = None
    complete_course: Optional[bool] = False
    experience_course: Optional[bool] = False


class CustomerDeleteRequest(BaseModel):
    ids: list[int]


class CustomerUpdate(BaseModel):
    name: str
    phone: str
    email: Optional[str] = ""
    birthday: Optional[date] = None
    complete_course: Optional[bool] = False
    complete_purchased: Optional[bool] = False
    experience_course: Optional[bool] = False
    experience_purchased: Optional[bool] = False


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


@router.post("/")
async def create_customer(customer_data: CustomerCreate, db: AsyncSession = Depends(get_db)):
    """新增顧客"""
    # 檢查電話是否已存在
    phone = customer_data.phone.zfill(10)
    result = await db.execute(
        select(Customer).where(Customer.phone == phone)
    )
    existing = result.scalar_one_or_none()

    if existing:
        raise HTTPException(status_code=400, detail="此電話號碼已存在")

    customer = Customer(
        name=customer_data.name,
        phone=phone,
        email=customer_data.email or "",
        birthday=customer_data.birthday
    )
    db.add(customer)
    await db.flush()

    # 處理課程歸類
    courses_added = []

    if customer_data.complete_course:
        # 取得或建立完整課程
        result = await db.execute(
            select(Course).where(Course.course_type == "完整課程").limit(1)
        )
        course = result.scalar_one_or_none()
        if not course:
            course = Course(name="完整課程", course_type="完整課程")
            db.add(course)
            await db.flush()

        participation = ActivityParticipation(
            customer_id=customer.id,
            course_id=course.id,
            activity_time=datetime.now(),
            purchased=False
        )
        db.add(participation)
        courses_added.append("完整課程")

    if customer_data.experience_course:
        # 取得或建立體驗課程
        result = await db.execute(
            select(Course).where(Course.course_type == "體驗課程").limit(1)
        )
        course = result.scalar_one_or_none()
        if not course:
            course = Course(name="體驗課程", course_type="體驗課程")
            db.add(course)
            await db.flush()

        participation = ActivityParticipation(
            customer_id=customer.id,
            course_id=course.id,
            activity_time=datetime.now(),
            purchased=False
        )
        db.add(participation)
        courses_added.append("體驗課程")

    await db.commit()
    await db.refresh(customer)

    message = f"顧客「{customer.name}」新增成功"
    if courses_added:
        message += f"，已加入：{', '.join(courses_added)}"

    return {
        "success": True,
        "message": message,
        "customer": {
            "id": customer.id,
            "name": customer.name,
            "phone": customer.phone,
            "email": customer.email,
            "birthday": str(customer.birthday) if customer.birthday else None
        }
    }


@router.get("/detail/{customer_id}")
async def get_customer_detail(customer_id: int, db: AsyncSession = Depends(get_db)):
    """取得顧客詳細資料（含課程狀態）"""
    result = await db.execute(
        select(Customer).where(Customer.id == customer_id)
    )
    customer = result.scalar_one_or_none()

    if not customer:
        raise HTTPException(status_code=404, detail="顧客不存在")

    # 取得課程參與狀態
    participations = await db.execute(
        select(ActivityParticipation, Course)
        .join(Course)
        .where(ActivityParticipation.customer_id == customer_id)
    )

    complete_course = False
    complete_purchased = False
    experience_course = False
    experience_purchased = False

    for participation, course in participations:
        if course.course_type == "完整課程":
            complete_course = True
            if participation.purchased:
                complete_purchased = True
        elif course.course_type == "體驗課程":
            experience_course = True
            if participation.purchased:
                experience_purchased = True

    return {
        "id": customer.id,
        "name": customer.name,
        "phone": customer.phone,
        "email": customer.email,
        "birthday": str(customer.birthday) if customer.birthday else None,
        "complete_course": complete_course,
        "complete_purchased": complete_purchased,
        "experience_course": experience_course,
        "experience_purchased": experience_purchased
    }


@router.put("/{customer_id}")
async def update_customer(customer_id: int, data: CustomerUpdate, db: AsyncSession = Depends(get_db)):
    """更新顧客資料"""
    result = await db.execute(
        select(Customer).where(Customer.id == customer_id)
    )
    customer = result.scalar_one_or_none()

    if not customer:
        raise HTTPException(status_code=404, detail="顧客不存在")

    # 更新基本資料
    customer.name = data.name
    customer.phone = data.phone.zfill(10)
    customer.email = data.email or ""
    customer.birthday = data.birthday

    # 處理完整課程
    result = await db.execute(
        select(Course).where(Course.course_type == "完整課程").limit(1)
    )
    complete_course = result.scalar_one_or_none()

    result = await db.execute(
        select(ActivityParticipation)
        .join(Course)
        .where(
            ActivityParticipation.customer_id == customer_id,
            Course.course_type == "完整課程"
        )
    )
    complete_participation = result.scalar_one_or_none()

    if data.complete_course:
        if not complete_course:
            complete_course = Course(name="完整課程", course_type="完整課程")
            db.add(complete_course)
            await db.flush()

        if complete_participation:
            complete_participation.purchased = data.complete_purchased
        else:
            participation = ActivityParticipation(
                customer_id=customer_id,
                course_id=complete_course.id,
                activity_time=datetime.now(),
                purchased=data.complete_purchased
            )
            db.add(participation)
    elif complete_participation:
        await db.delete(complete_participation)

    # 處理體驗課程
    result = await db.execute(
        select(Course).where(Course.course_type == "體驗課程").limit(1)
    )
    experience_course = result.scalar_one_or_none()

    result = await db.execute(
        select(ActivityParticipation)
        .join(Course)
        .where(
            ActivityParticipation.customer_id == customer_id,
            Course.course_type == "體驗課程"
        )
    )
    experience_participation = result.scalar_one_or_none()

    if data.experience_course:
        if not experience_course:
            experience_course = Course(name="體驗課程", course_type="體驗課程")
            db.add(experience_course)
            await db.flush()

        if experience_participation:
            experience_participation.purchased = data.experience_purchased
        else:
            participation = ActivityParticipation(
                customer_id=customer_id,
                course_id=experience_course.id,
                activity_time=datetime.now(),
                purchased=data.experience_purchased
            )
            db.add(participation)
    elif experience_participation:
        await db.delete(experience_participation)

    await db.commit()

    return {
        "success": True,
        "message": f"顧客「{customer.name}」資料更新成功"
    }


@router.delete("/")
async def delete_customers(request: CustomerDeleteRequest, db: AsyncSession = Depends(get_db)):
    """刪除多個顧客"""
    if not request.ids:
        raise HTTPException(status_code=400, detail="請選擇要刪除的顧客")

    # 先刪除相關的活動參與記錄
    await db.execute(
        delete(ActivityParticipation).where(
            ActivityParticipation.customer_id.in_(request.ids)
        )
    )

    # 刪除顧客
    result = await db.execute(
        delete(Customer).where(Customer.id.in_(request.ids))
    )
    await db.commit()

    deleted_count = result.rowcount

    return {
        "success": True,
        "message": f"已刪除 {deleted_count} 位顧客",
        "deleted": deleted_count
    }


@router.delete("/all")
async def delete_all_customers(db: AsyncSession = Depends(get_db)):
    """刪除所有顧客"""
    # 先刪除所有活動參與記錄
    await db.execute(delete(ActivityParticipation))

    # 刪除所有顧客
    result = await db.execute(delete(Customer))
    await db.commit()

    deleted_count = result.rowcount

    return {
        "success": True,
        "message": f"已刪除所有顧客（共 {deleted_count} 位）",
        "deleted": deleted_count
    }
