"""排程服務 - 使用 APScheduler 管理定時任務"""
import logging
from datetime import datetime
from typing import Callable, Optional, Any
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.jobstores.memory import MemoryJobStore

logger = logging.getLogger(__name__)


class SchedulerService:
    """排程服務"""

    def __init__(self):
        self.scheduler: Optional[AsyncIOScheduler] = None

    def init_scheduler(self):
        """初始化排程器"""
        jobstores = {
            'default': MemoryJobStore()
        }

        self.scheduler = AsyncIOScheduler(
            jobstores=jobstores,
            timezone='Asia/Taipei'
        )
        logger.info("Scheduler initialized")

    def start(self):
        """啟動排程器"""
        if self.scheduler and not self.scheduler.running:
            self.scheduler.start()
            logger.info("Scheduler started")

    def shutdown(self):
        """關閉排程器"""
        if self.scheduler and self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("Scheduler shutdown")

    def schedule_once(
        self,
        job_id: str,
        func: Callable,
        run_at: datetime,
        args: list = None,
        kwargs: dict = None
    ) -> str:
        """排程單次任務"""
        if not self.scheduler:
            raise RuntimeError("Scheduler not initialized")

        self.scheduler.add_job(
            func,
            trigger=DateTrigger(run_date=run_at),
            id=job_id,
            args=args or [],
            kwargs=kwargs or {},
            replace_existing=True
        )

        logger.info(f"Scheduled job {job_id} to run at {run_at}")
        return job_id

    def schedule_recurring(
        self,
        job_id: str,
        func: Callable,
        cron_expression: str,
        args: list = None,
        kwargs: dict = None
    ) -> str:
        """
        排程重複任務

        cron_expression 格式: "minute hour day month day_of_week"
        例如: "0 9 * * *" = 每天早上 9 點
        """
        if not self.scheduler:
            raise RuntimeError("Scheduler not initialized")

        # 解析 cron 表達式
        parts = cron_expression.split()
        if len(parts) != 5:
            raise ValueError("Invalid cron expression. Expected format: 'minute hour day month day_of_week'")

        trigger = CronTrigger(
            minute=parts[0],
            hour=parts[1],
            day=parts[2],
            month=parts[3],
            day_of_week=parts[4],
            timezone='Asia/Taipei'
        )

        self.scheduler.add_job(
            func,
            trigger=trigger,
            id=job_id,
            args=args or [],
            kwargs=kwargs or {},
            replace_existing=True
        )

        logger.info(f"Scheduled recurring job {job_id} with cron: {cron_expression}")
        return job_id

    def cancel_job(self, job_id: str) -> bool:
        """取消排程任務"""
        if not self.scheduler:
            return False

        try:
            self.scheduler.remove_job(job_id)
            logger.info(f"Cancelled job {job_id}")
            return True
        except Exception as e:
            logger.warning(f"Failed to cancel job {job_id}: {e}")
            return False

    def get_job(self, job_id: str) -> Optional[Any]:
        """取得任務資訊"""
        if not self.scheduler:
            return None
        return self.scheduler.get_job(job_id)

    def get_all_jobs(self) -> list:
        """取得所有任務"""
        if not self.scheduler:
            return []
        return self.scheduler.get_jobs()

    def job_exists(self, job_id: str) -> bool:
        """檢查任務是否存在"""
        return self.get_job(job_id) is not None


# 單例實例
scheduler_service = SchedulerService()
