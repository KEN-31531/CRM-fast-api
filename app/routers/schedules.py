"""排程管理 API 路由"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.database import get_db
from app.models.db_models import ScheduledTask
from app.services.scheduler_service import scheduler_service

router = APIRouter(prefix="/schedules", tags=["排程"])


# ========== Schemas ==========

class RecurringTaskCreate(BaseModel):
    task_type: str
    cron_expression: str  # 格式: "minute hour day month day_of_week"
    description: str


# ========== Endpoints ==========

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
