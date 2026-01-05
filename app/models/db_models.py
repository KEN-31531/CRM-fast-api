from sqlalchemy import String, Date, DateTime, Boolean, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import date, datetime
from typing import Optional
from app.database import Base


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(200), nullable=True)
    birthday: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    participations: Mapped[list["ActivityParticipation"]] = relationship(
        back_populates="customer"
    )


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    course_type: Mapped[str] = mapped_column(String(50))  # "完整課程" or "體驗課程"
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    participations: Mapped[list["ActivityParticipation"]] = relationship(
        back_populates="course"
    )


class ActivityParticipation(Base):
    __tablename__ = "activity_participations"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"))
    activity_time: Mapped[datetime] = mapped_column(DateTime)
    purchased: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    customer: Mapped["Customer"] = relationship(back_populates="participations")
    course: Mapped["Course"] = relationship(back_populates="participations")


# ==================== 廣告活動相關模型 ====================

class Campaign(Base):
    """廣告活動"""
    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    subject: Mapped[str] = mapped_column(String(500))
    content: Mapped[str] = mapped_column(Text)  # HTML 格式

    # 目標客群篩選條件
    course_type_filter: Mapped[str] = mapped_column(String(50), default="all")  # all, complete, experience
    purchase_status_filter: Mapped[str] = mapped_column(String(50), default="all")  # all, purchased, not_purchased

    # 狀態: draft, scheduled, sending, completed, cancelled
    status: Mapped[str] = mapped_column(String(50), default="draft")

    # 排程
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # 統計
    total_recipients: Mapped[int] = mapped_column(Integer, default=0)
    sent_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    # 關聯
    recipients: Mapped[list["CampaignRecipient"]] = relationship(back_populates="campaign", cascade="all, delete-orphan")
    tracked_links: Mapped[list["TrackedLink"]] = relationship(back_populates="campaign", cascade="all, delete-orphan")


class CampaignRecipient(Base):
    """活動收件人"""
    __tablename__ = "campaign_recipients"

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"))
    customer_id: Mapped[Optional[int]] = mapped_column(ForeignKey("customers.id"), nullable=True)

    # 額外的 email（沒有對應顧客時使用）
    email: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # 收件人名稱

    # 發送狀態
    sent: Mapped[bool] = mapped_column(Boolean, default=False)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # 追蹤
    clicked: Mapped[bool] = mapped_column(Boolean, default=False)
    clicked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    campaign: Mapped["Campaign"] = relationship(back_populates="recipients")
    customer: Mapped[Optional["Customer"]] = relationship()


class TrackedLink(Base):
    """追蹤連結"""
    __tablename__ = "tracked_links"

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"))

    # 連結資訊
    tracking_code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    original_url: Mapped[str] = mapped_column(String(2000))
    label: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)  # 連結標籤

    # 統計
    click_count: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    campaign: Mapped["Campaign"] = relationship(back_populates="tracked_links")
    clicks: Mapped[list["LinkClick"]] = relationship(back_populates="tracked_link", cascade="all, delete-orphan")


class LinkClick(Base):
    """連結點擊記錄"""
    __tablename__ = "link_clicks"

    id: Mapped[int] = mapped_column(primary_key=True)
    tracked_link_id: Mapped[int] = mapped_column(ForeignKey("tracked_links.id", ondelete="CASCADE"))
    recipient_id: Mapped[Optional[int]] = mapped_column(ForeignKey("campaign_recipients.id", ondelete="SET NULL"), nullable=True)

    # 點擊資訊
    clicked_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    ip_address: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    tracked_link: Mapped["TrackedLink"] = relationship(back_populates="clicks")


class ScheduledTask(Base):
    """排程任務記錄"""
    __tablename__ = "scheduled_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_type: Mapped[str] = mapped_column(String(50))  # campaign, birthday_greeting, etc.
    reference_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # campaign_id 等

    # 排程設定
    job_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # 重複設定
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False)
    cron_expression: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # 任務參數（JSON 格式儲存）
    task_params: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # 狀態: pending, running, completed, failed, cancelled
    status: Mapped[str] = mapped_column(String(50), default="pending")
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    next_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
