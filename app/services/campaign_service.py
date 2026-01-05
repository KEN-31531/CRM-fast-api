"""廣告活動服務 - 處理活動建立、發送、追蹤等邏輯"""
import uuid
import re
import logging
from datetime import datetime
from typing import Optional
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.db_models import (
    Campaign, CampaignRecipient, TrackedLink, LinkClick,
    Customer, ActivityParticipation, Course, ScheduledTask
)
from app.services.email_service import email_service

logger = logging.getLogger(__name__)


class CampaignService:
    """廣告活動服務"""

    async def get_filtered_customers(
        self,
        db: AsyncSession,
        course_type_filter: str,
        purchase_status_filter: str
    ) -> list[Customer]:
        """
        根據篩選條件取得目標客群

        Args:
            course_type_filter: all, complete, experience
            purchase_status_filter: all, purchased, not_purchased
        """
        # 基礎查詢：有 email 的顧客
        if course_type_filter == "all" and purchase_status_filter == "all":
            query = select(Customer).where(Customer.email.isnot(None))
            result = await db.execute(query)
            return list(result.scalars().all())

        # 課程類型對應
        course_type_map = {
            "complete": "完整課程",
            "experience": "體驗課程"
        }

        # 建立子查詢
        subquery = (
            select(ActivityParticipation.customer_id)
            .join(Course, ActivityParticipation.course_id == Course.id)
        )

        # 課程類型篩選
        if course_type_filter != "all":
            course_type = course_type_map.get(course_type_filter)
            if course_type:
                subquery = subquery.where(Course.course_type == course_type)

        # 購買狀態篩選
        if purchase_status_filter == "purchased":
            subquery = subquery.where(ActivityParticipation.purchased == True)
        elif purchase_status_filter == "not_purchased":
            subquery = subquery.where(ActivityParticipation.purchased == False)

        subquery = subquery.distinct()

        # 主查詢
        query = (
            select(Customer)
            .where(Customer.email.isnot(None))
            .where(Customer.id.in_(subquery))
        )

        result = await db.execute(query)
        return list(result.scalars().all())

    def generate_tracking_code(self) -> str:
        """生成追蹤碼"""
        return str(uuid.uuid4())[:8]

    def process_content_with_tracking(
        self,
        content: str,
        campaign_id: int,
        recipient_id: int,
        base_url: str
    ) -> tuple[str, list[dict]]:
        """
        處理郵件內容，將連結替換為追蹤連結

        Returns:
            (處理後的內容, 追蹤連結列表)
        """
        tracked_links = []

        # 找出所有 href 連結
        link_pattern = r'href=["\']([^"\']+)["\']'

        def replace_link(match):
            original_url = match.group(1)

            # 跳過 mailto:, tel:, # 開頭的連結
            if original_url.startswith(('mailto:', '#', 'tel:', 'javascript:')):
                return match.group(0)

            # 生成追蹤碼
            tracking_code = self.generate_tracking_code()
            tracking_url = f"{base_url}/t/{tracking_code}?r={recipient_id}"

            tracked_links.append({
                "tracking_code": tracking_code,
                "original_url": original_url,
                "campaign_id": campaign_id
            })

            return f'href="{tracking_url}"'

        processed_content = re.sub(link_pattern, replace_link, content)

        return processed_content, tracked_links

    async def create_campaign(
        self,
        db: AsyncSession,
        name: str,
        subject: str,
        content: str,
        course_type_filter: str = "all",
        purchase_status_filter: str = "all",
        customer_ids: list[int] = None,
        additional_emails: list[str] = None,
        use_filter: bool = True
    ) -> Campaign:
        """建立廣告活動"""
        campaign = Campaign(
            name=name,
            subject=subject,
            content=content,
            course_type_filter=course_type_filter,
            purchase_status_filter=purchase_status_filter,
            status="draft"
        )
        db.add(campaign)
        await db.commit()
        await db.refresh(campaign)

        added_customer_ids = set()
        added_emails = set()
        total_recipients = 0

        # 1. 如果使用篩選條件，取得符合條件的顧客
        if use_filter:
            customers = await self.get_filtered_customers(
                db, course_type_filter, purchase_status_filter
            )
            for customer in customers:
                if customer.id not in added_customer_ids:
                    recipient = CampaignRecipient(
                        campaign_id=campaign.id,
                        customer_id=customer.id
                    )
                    db.add(recipient)
                    added_customer_ids.add(customer.id)
                    total_recipients += 1

        # 2. 如果有指定 customer_ids，加入這些顧客
        if customer_ids:
            result = await db.execute(
                select(Customer).where(Customer.id.in_(customer_ids))
            )
            specified_customers = result.scalars().all()
            for customer in specified_customers:
                if customer.id not in added_customer_ids:
                    recipient = CampaignRecipient(
                        campaign_id=campaign.id,
                        customer_id=customer.id
                    )
                    db.add(recipient)
                    added_customer_ids.add(customer.id)
                    total_recipients += 1

        # 3. 如果有額外的 email，建立沒有 customer_id 的收件人
        if additional_emails:
            for email in additional_emails:
                email = email.strip().lower()
                if email and email not in added_emails:
                    # 檢查是否已經在顧客列表中
                    existing = await db.execute(
                        select(Customer).where(Customer.email == email)
                    )
                    existing_customer = existing.scalar_one_or_none()

                    if existing_customer and existing_customer.id in added_customer_ids:
                        # 已經加入過了，跳過
                        continue
                    elif existing_customer:
                        # 有對應顧客但還沒加入
                        recipient = CampaignRecipient(
                            campaign_id=campaign.id,
                            customer_id=existing_customer.id
                        )
                        added_customer_ids.add(existing_customer.id)
                    else:
                        # 沒有對應顧客，建立只有 email 的收件人
                        recipient = CampaignRecipient(
                            campaign_id=campaign.id,
                            email=email,
                            name=email.split("@")[0]  # 使用 email 前綴作為預設名稱
                        )

                    db.add(recipient)
                    added_emails.add(email)
                    total_recipients += 1

        campaign.total_recipients = total_recipients
        await db.commit()

        logger.info(f"Created campaign {campaign.id} with {total_recipients} recipients")
        return campaign

    async def update_campaign(
        self,
        db: AsyncSession,
        campaign_id: int,
        **kwargs
    ) -> Optional[Campaign]:
        """更新廣告活動"""
        result = await db.execute(
            select(Campaign).where(Campaign.id == campaign_id)
        )
        campaign = result.scalar_one_or_none()

        if not campaign or campaign.status != "draft":
            return None

        for key, value in kwargs.items():
            if hasattr(campaign, key) and value is not None:
                setattr(campaign, key, value)

        # 如果篩選條件改變，重新計算收件人
        if 'course_type_filter' in kwargs or 'purchase_status_filter' in kwargs:
            # 刪除舊的收件人
            await db.execute(
                select(CampaignRecipient)
                .where(CampaignRecipient.campaign_id == campaign_id)
            )
            # 這裡簡化處理，實際應該刪除並重建

        await db.commit()
        await db.refresh(campaign)
        return campaign

    async def get_campaign(
        self,
        db: AsyncSession,
        campaign_id: int
    ) -> Optional[Campaign]:
        """取得單一廣告活動"""
        result = await db.execute(
            select(Campaign)
            .options(selectinload(Campaign.recipients))
            .options(selectinload(Campaign.tracked_links))
            .where(Campaign.id == campaign_id)
        )
        return result.scalar_one_or_none()

    async def get_all_campaigns(self, db: AsyncSession) -> list[Campaign]:
        """取得所有廣告活動"""
        result = await db.execute(
            select(Campaign).order_by(Campaign.created_at.desc())
        )
        return list(result.scalars().all())

    async def delete_campaign(
        self,
        db: AsyncSession,
        campaign_id: int
    ) -> bool:
        """刪除廣告活動（僅限草稿）"""
        result = await db.execute(
            select(Campaign).where(Campaign.id == campaign_id)
        )
        campaign = result.scalar_one_or_none()

        if not campaign or campaign.status != "draft":
            return False

        await db.delete(campaign)
        await db.commit()
        return True

    async def send_campaign(
        self,
        db: AsyncSession,
        campaign_id: int,
        base_url: str = "http://localhost:8000"
    ) -> dict:
        """發送廣告活動"""
        # 取得活動
        result = await db.execute(
            select(Campaign)
            .options(selectinload(Campaign.recipients).selectinload(CampaignRecipient.customer))
            .where(Campaign.id == campaign_id)
        )
        campaign = result.scalar_one_or_none()

        if not campaign:
            return {"success": False, "error": "活動不存在"}

        if campaign.status not in ["draft", "scheduled"]:
            return {"success": False, "error": f"活動狀態不正確: {campaign.status}"}

        # 更新狀態
        campaign.status = "sending"
        campaign.sent_at = datetime.now()
        await db.commit()

        sent_count = 0
        failed_count = 0

        for recipient in campaign.recipients:
            if recipient.sent:
                continue

            # 取得收件人資訊（可能來自 customer 或直接設定的 email）
            customer = recipient.customer
            if customer:
                recipient_email = customer.email
                recipient_name = customer.name
            else:
                recipient_email = recipient.email
                recipient_name = recipient.name or "收件人"

            if not recipient_email:
                recipient.error_message = "無效的 Email"
                failed_count += 1
                continue

            try:
                # 個人化內容
                personalized_content = campaign.content.replace(
                    "{{name}}", recipient_name
                )

                # 處理追蹤連結
                processed_content, tracked_links = self.process_content_with_tracking(
                    personalized_content,
                    campaign.id,
                    recipient.id,
                    base_url
                )

                # 儲存追蹤連結
                for link_data in tracked_links:
                    tracked_link = TrackedLink(
                        campaign_id=link_data["campaign_id"],
                        tracking_code=link_data["tracking_code"],
                        original_url=link_data["original_url"]
                    )
                    db.add(tracked_link)

                # 發送郵件
                send_result = await email_service.send_email(
                    to=recipient_email,
                    subject=campaign.subject,
                    body_html=processed_content
                )

                if send_result.get("success"):
                    recipient.sent = True
                    recipient.sent_at = datetime.now()
                    sent_count += 1
                else:
                    recipient.error_message = send_result.get("error", "發送失敗")
                    failed_count += 1

            except Exception as e:
                logger.error(f"Failed to send to {recipient_email}: {e}")
                recipient.error_message = str(e)
                failed_count += 1

            await db.commit()

        # 更新活動統計
        campaign.status = "completed"
        campaign.sent_count = sent_count
        campaign.failed_count = failed_count
        await db.commit()

        logger.info(f"Campaign {campaign_id} completed: {sent_count} sent, {failed_count} failed")

        return {
            "success": True,
            "sent_count": sent_count,
            "failed_count": failed_count,
            "total": campaign.total_recipients
        }

    async def get_campaign_stats(
        self,
        db: AsyncSession,
        campaign_id: int
    ) -> dict:
        """取得活動統計"""
        result = await db.execute(
            select(Campaign)
            .options(selectinload(Campaign.recipients))
            .options(selectinload(Campaign.tracked_links).selectinload(TrackedLink.clicks))
            .where(Campaign.id == campaign_id)
        )
        campaign = result.scalar_one_or_none()

        if not campaign:
            return {}

        # 計算點擊統計
        total_clicks = sum(link.click_count for link in campaign.tracked_links)
        unique_clickers = len([r for r in campaign.recipients if r.clicked])

        click_rate = 0
        if campaign.sent_count > 0:
            click_rate = round(unique_clickers / campaign.sent_count * 100, 2)

        return {
            "campaign_id": campaign.id,
            "name": campaign.name,
            "status": campaign.status,
            "total_recipients": campaign.total_recipients,
            "sent_count": campaign.sent_count,
            "failed_count": campaign.failed_count,
            "total_clicks": total_clicks,
            "unique_clickers": unique_clickers,
            "click_rate": click_rate,
            "links": [
                {
                    "tracking_code": link.tracking_code,
                    "original_url": link.original_url,
                    "click_count": link.click_count
                }
                for link in campaign.tracked_links
            ]
        }


# 單例實例
campaign_service = CampaignService()


# 給排程器調用的函數
async def execute_scheduled_campaign(campaign_id: int):
    """執行排程的廣告活動"""
    from app.database import async_session

    async with async_session() as db:
        result = await campaign_service.send_campaign(db, campaign_id)
        logger.info(f"Scheduled campaign {campaign_id} result: {result}")
        return result
