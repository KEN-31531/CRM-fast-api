"""廣告活動 API 路由"""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
from typing import Optional

from app.database import get_db
from app.services.campaign_service import campaign_service, execute_scheduled_campaign
from app.services.scheduler_service import scheduler_service
from app.models.db_models import Campaign, ScheduledTask

router = APIRouter(prefix="/campaigns", tags=["廣告活動"])


# ========== Schemas ==========

class CampaignCreate(BaseModel):
    name: str
    subject: str
    content: str
    course_type_filter: str = "all"  # all, complete, experience
    purchase_status_filter: str = "all"  # all, purchased, not_purchased
    # 新增：可以直接指定收件人
    customer_ids: Optional[list[int]] = None  # 指定的顧客 ID 列表
    additional_emails: Optional[list[str]] = None  # 額外的 email 地址
    use_filter: bool = True  # 是否使用篩選條件（False = 僅使用指定的收件人）


class CampaignUpdate(BaseModel):
    name: Optional[str] = None
    subject: Optional[str] = None
    content: Optional[str] = None
    course_type_filter: Optional[str] = None
    purchase_status_filter: Optional[str] = None


class CampaignSchedule(BaseModel):
    scheduled_at: datetime


class CampaignResponse(BaseModel):
    id: int
    name: str
    subject: str
    status: str
    total_recipients: int
    sent_count: int
    failed_count: int
    scheduled_at: Optional[datetime]
    sent_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


# ========== Endpoints ==========

@router.get("/")
async def list_campaigns(
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """列出所有廣告活動"""
    campaigns = await campaign_service.get_all_campaigns(db)

    if status:
        campaigns = [c for c in campaigns if c.status == status]

    return [
        {
            "id": c.id,
            "name": c.name,
            "subject": c.subject,
            "status": c.status,
            "course_type_filter": c.course_type_filter,
            "purchase_status_filter": c.purchase_status_filter,
            "total_recipients": c.total_recipients,
            "sent_count": c.sent_count,
            "failed_count": c.failed_count,
            "scheduled_at": c.scheduled_at.isoformat() if c.scheduled_at else None,
            "sent_at": c.sent_at.isoformat() if c.sent_at else None,
            "created_at": c.created_at.isoformat()
        }
        for c in campaigns
    ]


@router.post("/")
async def create_campaign(
    campaign: CampaignCreate,
    db: AsyncSession = Depends(get_db)
):
    """建立新廣告活動"""
    new_campaign = await campaign_service.create_campaign(
        db,
        name=campaign.name,
        subject=campaign.subject,
        content=campaign.content,
        course_type_filter=campaign.course_type_filter,
        purchase_status_filter=campaign.purchase_status_filter,
        customer_ids=campaign.customer_ids,
        additional_emails=campaign.additional_emails,
        use_filter=campaign.use_filter
    )

    return {
        "success": True,
        "campaign_id": new_campaign.id,
        "total_recipients": new_campaign.total_recipients,
        "message": f"活動已建立，共 {new_campaign.total_recipients} 位收件人"
    }


@router.get("/{campaign_id}")
async def get_campaign(
    campaign_id: int,
    db: AsyncSession = Depends(get_db)
):
    """取得單一廣告活動詳情"""
    campaign = await campaign_service.get_campaign(db, campaign_id)

    if not campaign:
        raise HTTPException(status_code=404, detail="活動不存在")

    return {
        "id": campaign.id,
        "name": campaign.name,
        "subject": campaign.subject,
        "content": campaign.content,
        "status": campaign.status,
        "course_type_filter": campaign.course_type_filter,
        "purchase_status_filter": campaign.purchase_status_filter,
        "total_recipients": campaign.total_recipients,
        "sent_count": campaign.sent_count,
        "failed_count": campaign.failed_count,
        "scheduled_at": campaign.scheduled_at.isoformat() if campaign.scheduled_at else None,
        "sent_at": campaign.sent_at.isoformat() if campaign.sent_at else None,
        "created_at": campaign.created_at.isoformat()
    }


@router.put("/{campaign_id}")
async def update_campaign(
    campaign_id: int,
    campaign: CampaignUpdate,
    db: AsyncSession = Depends(get_db)
):
    """更新廣告活動（僅限草稿狀態）"""
    updated = await campaign_service.update_campaign(
        db,
        campaign_id,
        **campaign.model_dump(exclude_unset=True)
    )

    if not updated:
        raise HTTPException(
            status_code=400,
            detail="無法更新活動（可能不存在或非草稿狀態）"
        )

    return {"success": True, "message": "活動已更新"}


@router.delete("/{campaign_id}")
async def delete_campaign(
    campaign_id: int,
    db: AsyncSession = Depends(get_db)
):
    """刪除廣告活動（僅限草稿狀態）"""
    deleted = await campaign_service.delete_campaign(db, campaign_id)

    if not deleted:
        raise HTTPException(
            status_code=400,
            detail="無法刪除活動（可能不存在或非草稿狀態）"
        )

    return {"success": True, "message": "活動已刪除"}


@router.get("/{campaign_id}/preview-recipients")
async def preview_recipients(
    campaign_id: int,
    db: AsyncSession = Depends(get_db)
):
    """預覽符合篩選條件的收件人列表"""
    campaign = await campaign_service.get_campaign(db, campaign_id)

    if not campaign:
        raise HTTPException(status_code=404, detail="活動不存在")

    customers = await campaign_service.get_filtered_customers(
        db,
        campaign.course_type_filter,
        campaign.purchase_status_filter
    )

    return {
        "total": len(customers),
        "customers": [
            {
                "id": c.id,
                "name": c.name,
                "email": c.email[:3] + "***" + c.email[c.email.index("@"):] if c.email and "@" in c.email else c.email
            }
            for c in customers[:50]  # 只返回前 50 筆預覽
        ]
    }


@router.post("/{campaign_id}/schedule")
async def schedule_campaign(
    campaign_id: int,
    schedule: CampaignSchedule,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """排程發送廣告活動"""
    campaign = await campaign_service.get_campaign(db, campaign_id)

    if not campaign:
        raise HTTPException(status_code=404, detail="活動不存在")

    if campaign.status != "draft":
        raise HTTPException(status_code=400, detail="只有草稿狀態的活動可以排程")

    if schedule.scheduled_at <= datetime.now():
        raise HTTPException(status_code=400, detail="排程時間必須是未來時間")

    # 更新活動狀態
    campaign.status = "scheduled"
    campaign.scheduled_at = schedule.scheduled_at

    # 建立排程任務
    job_id = f"campaign_{campaign_id}"

    # 取得 base_url
    base_url = str(request.base_url).rstrip('/')

    scheduler_service.schedule_once(
        job_id=job_id,
        func=execute_scheduled_campaign,
        run_at=schedule.scheduled_at,
        kwargs={"campaign_id": campaign_id}
    )

    # 記錄排程任務
    task = ScheduledTask(
        task_type="campaign",
        reference_id=campaign_id,
        job_id=job_id,
        scheduled_at=schedule.scheduled_at,
        description=f"發送廣告活動: {campaign.name}",
        status="pending"
    )
    db.add(task)

    await db.commit()

    return {
        "success": True,
        "message": f"活動已排程於 {schedule.scheduled_at.strftime('%Y-%m-%d %H:%M')} 發送",
        "job_id": job_id
    }


@router.post("/{campaign_id}/send-now")
async def send_campaign_now(
    campaign_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """立即發送廣告活動"""
    campaign = await campaign_service.get_campaign(db, campaign_id)

    if not campaign:
        raise HTTPException(status_code=404, detail="活動不存在")

    if campaign.status not in ["draft", "scheduled"]:
        raise HTTPException(status_code=400, detail=f"活動狀態不正確: {campaign.status}")

    # 取得 base_url
    base_url = str(request.base_url).rstrip('/')

    # 在背景執行發送
    result = await campaign_service.send_campaign(db, campaign_id, base_url)

    return {
        "success": result.get("success", False),
        "message": f"發送完成：成功 {result.get('sent_count', 0)} 封，失敗 {result.get('failed_count', 0)} 封",
        **result
    }


@router.post("/{campaign_id}/cancel")
async def cancel_campaign(
    campaign_id: int,
    db: AsyncSession = Depends(get_db)
):
    """取消排程的廣告活動"""
    campaign = await campaign_service.get_campaign(db, campaign_id)

    if not campaign:
        raise HTTPException(status_code=404, detail="活動不存在")

    if campaign.status != "scheduled":
        raise HTTPException(status_code=400, detail="只能取消已排程的活動")

    # 取消排程任務
    job_id = f"campaign_{campaign_id}"
    scheduler_service.cancel_job(job_id)

    # 更新活動狀態
    campaign.status = "cancelled"
    await db.commit()

    return {"success": True, "message": "活動已取消"}


@router.get("/{campaign_id}/stats")
async def get_campaign_stats(
    campaign_id: int,
    db: AsyncSession = Depends(get_db)
):
    """取得廣告活動統計數據"""
    stats = await campaign_service.get_campaign_stats(db, campaign_id)

    if not stats:
        raise HTTPException(status_code=404, detail="活動不存在")

    return stats
