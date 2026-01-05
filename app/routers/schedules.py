"""排程管理 API 路由"""
import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.database import get_db, async_session
from app.models.db_models import ScheduledTask
from app.services.scheduler_service import scheduler_service

router = APIRouter(prefix="/schedules", tags=["排程"])


# ========== 重載排程任務 ==========

async def reload_scheduled_tasks():
    """伺服器啟動時從資料庫重新載入排程任務"""
    import logging
    from datetime import datetime

    logger = logging.getLogger(__name__)
    logger.info("正在從資料庫重新載入排程任務...")

    async with async_session() as db:
        # 取得所有 pending 狀態的任務
        result = await db.execute(
            select(ScheduledTask).where(ScheduledTask.status == "pending")
        )
        tasks = result.scalars().all()

        loaded_count = 0
        for task in tasks:
            try:
                # 解析任務參數
                params = json.loads(task.task_params) if task.task_params else {}

                # 建立任務函數
                task_type = task.task_type
                description = task.description
                customer_ids = params.get("customer_ids")
                additional_emails = params.get("additional_emails")
                email_subject = params.get("email_subject")
                email_content = params.get("email_content")

                async def make_task_func(tt, desc, cids, aes, subj, cont):
                    async def task_func():
                        await execute_task(
                            task_type=tt,
                            description=desc,
                            customer_ids=cids,
                            additional_emails=aes,
                            email_subject=subj,
                            email_content=cont
                        )
                    return task_func

                task_func = await make_task_func(
                    task_type, description, customer_ids,
                    additional_emails, email_subject, email_content
                )

                if task.is_recurring and task.cron_expression:
                    # 重複任務
                    scheduler_service.schedule_recurring(
                        job_id=task.job_id,
                        func=task_func,
                        cron_expression=task.cron_expression
                    )
                    loaded_count += 1
                    logger.info(f"重新載入重複任務: {task.job_id}")

                elif task.scheduled_at and task.scheduled_at > datetime.now():
                    # 單次任務（且尚未過期）
                    scheduler_service.schedule_once(
                        job_id=task.job_id,
                        func=task_func,
                        run_at=task.scheduled_at
                    )
                    loaded_count += 1
                    logger.info(f"重新載入單次任務: {task.job_id}")

                elif task.scheduled_at and task.scheduled_at <= datetime.now():
                    # 已過期的單次任務，標記為 missed
                    task.status = "missed"
                    await db.commit()
                    logger.warning(f"任務已過期: {task.job_id}")

            except Exception as e:
                logger.error(f"載入任務失敗 {task.job_id}: {e}")

        logger.info(f"排程任務重新載入完成，共載入 {loaded_count} 個任務")


# ========== Schemas ==========

class RecurringTaskCreate(BaseModel):
    task_type: str
    cron_expression: str  # 格式: "minute hour day month day_of_week"
    description: str
    # 收件人設定
    customer_ids: Optional[list[int]] = None  # 指定的顧客 ID 列表
    additional_emails: Optional[list[str]] = None  # 額外的 email 地址
    email_subject: Optional[str] = None  # 郵件主旨
    email_content: Optional[str] = None  # 郵件內容


class OnceTaskCreate(BaseModel):
    task_type: str
    scheduled_at: str  # ISO 格式: "2024-01-15T09:00:00"
    description: str
    # 收件人設定
    customer_ids: Optional[list[int]] = None  # 指定的顧客 ID 列表
    additional_emails: Optional[list[str]] = None  # 額外的 email 地址
    email_subject: Optional[str] = None  # 郵件主旨
    email_content: Optional[str] = None  # 郵件內容


# ========== 任務執行函數 ==========

async def execute_task(
    task_type: str,
    description: str = "",
    customer_ids: list[int] = None,
    additional_emails: list[str] = None,
    email_subject: str = None,
    email_content: str = None
):
    """執行排程任務"""
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"執行任務: {task_type} - {description}")

    from app.services.email_service import email_service
    from app.database import AsyncSessionLocal
    from sqlalchemy import select
    from app.models.db_models import Customer
    from datetime import datetime

    if task_type == "birthday_greeting":
        # 每日檢查生日並發送祝賀
        from sqlalchemy import extract

        async with AsyncSessionLocal() as session:
            today = datetime.now()
            result = await session.execute(
                select(Customer).where(
                    extract('month', Customer.birthday) == today.month,
                    extract('day', Customer.birthday) == today.day
                )
            )
            birthday_customers = result.scalars().all()

            for customer in birthday_customers:
                if customer.email:
                    await email_service.send_birthday_greeting(customer)

            logger.info(f"生日祝賀任務完成，發送給 {len(birthday_customers)} 位顧客")

    elif task_type in ["campaign_send", "reminder_email"] or customer_ids or additional_emails:
        # 發送郵件給指定的顧客
        if not email_subject or not email_content:
            logger.warning("缺少郵件主旨或內容")
            return {"success": False, "error": "缺少郵件主旨或內容"}

        sent_count = 0
        failed_count = 0

        async with AsyncSessionLocal() as session:
            # 發送給指定的顧客
            if customer_ids:
                result = await session.execute(
                    select(Customer).where(Customer.id.in_(customer_ids))
                )
                customers = result.scalars().all()

                for customer in customers:
                    if customer.email:
                        personalized_content = email_content.replace("{{name}}", customer.name)
                        send_result = await email_service.send_email(
                            to=customer.email,
                            subject=email_subject,
                            body_html=personalized_content
                        )
                        if send_result.get("success"):
                            sent_count += 1
                        else:
                            failed_count += 1

            # 發送給額外的 email
            if additional_emails:
                for email in additional_emails:
                    email = email.strip()
                    if email:
                        personalized_content = email_content.replace("{{name}}", email.split("@")[0])
                        send_result = await email_service.send_email(
                            to=email,
                            subject=email_subject,
                            body_html=personalized_content
                        )
                        if send_result.get("success"):
                            sent_count += 1
                        else:
                            failed_count += 1

        logger.info(f"郵件任務完成：發送 {sent_count} 封，失敗 {failed_count} 封")

    else:
        # 自訂任務 - 記錄執行
        logger.info(f"自訂任務執行: {task_type}")

    return {"success": True, "task_type": task_type}


# ========== Endpoints ==========

@router.post("/once")
async def create_once_task(
    task: OnceTaskCreate,
    db: AsyncSession = Depends(get_db)
):
    """建立單次排程任務"""
    import uuid
    from datetime import datetime

    job_id = f"once_{task.task_type}_{uuid.uuid4().hex[:8]}"

    # 解析時間
    try:
        scheduled_at = datetime.fromisoformat(task.scheduled_at)
    except ValueError:
        raise HTTPException(status_code=400, detail="時間格式錯誤，請使用 ISO 格式")

    if scheduled_at <= datetime.now():
        raise HTTPException(status_code=400, detail="排程時間必須是未來時間")

    # 建立任務函數（捕獲所有參數）
    task_type = task.task_type
    description = task.description
    customer_ids = task.customer_ids
    additional_emails = task.additional_emails
    email_subject = task.email_subject
    email_content = task.email_content

    async def task_func():
        await execute_task(
            task_type=task_type,
            description=description,
            customer_ids=customer_ids,
            additional_emails=additional_emails,
            email_subject=email_subject,
            email_content=email_content
        )

    # 新增排程
    job_id_result = scheduler_service.schedule_once(
        job_id=job_id,
        func=task_func,
        run_at=scheduled_at
    )

    if not job_id_result:
        raise HTTPException(status_code=500, detail="排程建立失敗")

    # 儲存任務參數為 JSON
    task_params = {
        "customer_ids": task.customer_ids,
        "additional_emails": task.additional_emails,
        "email_subject": task.email_subject,
        "email_content": task.email_content
    }

    # 儲存到資料庫
    db_task = ScheduledTask(
        job_id=job_id,
        task_type=task.task_type,
        description=task.description,
        is_recurring=False,
        scheduled_at=scheduled_at,
        task_params=json.dumps(task_params, ensure_ascii=False),
        status="pending"
    )
    db.add(db_task)
    await db.commit()

    return {
        "success": True,
        "message": f"排程已建立，將於 {scheduled_at.strftime('%Y-%m-%d %H:%M')} 執行",
        "job_id": job_id
    }


@router.get("/")
async def list_schedules(
    db: AsyncSession = Depends(get_db)
):
    """列出所有排程任務"""
    result = await db.execute(
        select(ScheduledTask).order_by(ScheduledTask.created_at.desc())
    )
    tasks = result.scalars().all()

    # 從排程器取得最新狀態
    scheduler_jobs = {job.id: job for job in scheduler_service.get_all_jobs()}

    return [
        {
            "id": task.id,
            "task_type": task.task_type,
            "job_id": task.job_id,
            "description": task.description,
            "scheduled_at": task.scheduled_at.isoformat() if task.scheduled_at else None,
            "is_recurring": task.is_recurring,
            "cron_expression": task.cron_expression,
            "status": task.status,
            "last_run_at": task.last_run_at.isoformat() if task.last_run_at else None,
            "next_run_at": (
                scheduler_jobs[task.job_id].next_run_time.isoformat()
                if task.job_id in scheduler_jobs and scheduler_jobs[task.job_id].next_run_time
                else None
            ),
            "created_at": task.created_at.isoformat()
        }
        for task in tasks
    ]


@router.get("/active")
async def list_active_jobs():
    """列出排程器中的活躍任務"""
    jobs = scheduler_service.get_all_jobs()

    return [
        {
            "job_id": job.id,
            "name": job.name,
            "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
            "trigger": str(job.trigger)
        }
        for job in jobs
    ]


@router.delete("/{job_id}")
async def cancel_schedule(
    job_id: str,
    db: AsyncSession = Depends(get_db)
):
    """取消排程任務"""
    # 從排程器取消
    cancelled = scheduler_service.cancel_job(job_id)

    # 更新資料庫記錄
    result = await db.execute(
        select(ScheduledTask).where(ScheduledTask.job_id == job_id)
    )
    task = result.scalar_one_or_none()

    if task:
        task.status = "cancelled"
        await db.commit()

    if not cancelled and not task:
        raise HTTPException(status_code=404, detail="任務不存在")

    return {"success": True, "message": "排程已取消"}


@router.post("/recurring")
async def create_recurring_task(
    task: RecurringTaskCreate,
    db: AsyncSession = Depends(get_db)
):
    """建立重複排程任務"""
    import uuid

    job_id = f"recurring_{task.task_type}_{uuid.uuid4().hex[:8]}"

    # 建立任務函數（捕獲所有參數）
    task_type = task.task_type
    description = task.description
    customer_ids = task.customer_ids
    additional_emails = task.additional_emails
    email_subject = task.email_subject
    email_content = task.email_content

    async def task_func():
        await execute_task(
            task_type=task_type,
            description=description,
            customer_ids=customer_ids,
            additional_emails=additional_emails,
            email_subject=email_subject,
            email_content=email_content
        )

    # 新增排程
    job_id_result = scheduler_service.schedule_recurring(
        job_id=job_id,
        func=task_func,
        cron_expression=task.cron_expression
    )

    if not job_id_result:
        raise HTTPException(status_code=500, detail="排程建立失敗")

    # 儲存任務參數為 JSON
    task_params = {
        "customer_ids": task.customer_ids,
        "additional_emails": task.additional_emails,
        "email_subject": task.email_subject,
        "email_content": task.email_content
    }

    # 儲存到資料庫
    db_task = ScheduledTask(
        job_id=job_id,
        task_type=task.task_type,
        description=task.description,
        is_recurring=True,
        cron_expression=task.cron_expression,
        task_params=json.dumps(task_params, ensure_ascii=False),
        status="pending"
    )
    db.add(db_task)
    await db.commit()

    return {"success": True, "message": "重複排程已建立", "job_id": job_id}


@router.get("/status/{job_id}")
async def get_schedule_status(
    job_id: str,
    db: AsyncSession = Depends(get_db)
):
    """取得排程任務狀態"""
    # 從資料庫取得記錄
    result = await db.execute(
        select(ScheduledTask).where(ScheduledTask.job_id == job_id)
    )
    task = result.scalar_one_or_none()

    # 從排程器取得狀態
    job = scheduler_service.get_job(job_id)

    if not task and not job:
        raise HTTPException(status_code=404, detail="任務不存在")

    return {
        "job_id": job_id,
        "task_type": task.task_type if task else None,
        "description": task.description if task else None,
        "status": task.status if task else ("active" if job else "unknown"),
        "is_recurring": task.is_recurring if task else False,
        "next_run_time": job.next_run_time.isoformat() if job and job.next_run_time else None,
        "last_run_at": task.last_run_at.isoformat() if task and task.last_run_at else None
    }
