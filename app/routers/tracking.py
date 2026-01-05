"""連結追蹤 API 路由"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from app.database import get_db
from app.models.db_models import TrackedLink, LinkClick, CampaignRecipient

router = APIRouter(prefix="/t", tags=["追蹤"])


@router.get("/{tracking_code}")
async def track_click(
    tracking_code: str,
    r: int = None,  # recipient_id
    request: Request = None,
    db: AsyncSession = Depends(get_db)
):
    """
    追蹤連結點擊並重新導向到目標 URL

    URL 格式: /t/{tracking_code}?r={recipient_id}
    """
    # 1. 查詢追蹤連結
    result = await db.execute(
        select(TrackedLink).where(TrackedLink.tracking_code == tracking_code)
    )
    tracked_link = result.scalar_one_or_none()

    if not tracked_link:
        # 連結不存在，重導向到首頁
        return RedirectResponse(url="/", status_code=302)

    # 2. 記錄點擊
    click = LinkClick(
        tracked_link_id=tracked_link.id,
        recipient_id=r,
        clicked_at=datetime.now(),
        ip_address=request.client.host if request and request.client else None,
        user_agent=request.headers.get("user-agent", "")[:500] if request else None
    )
    db.add(click)

    # 3. 更新追蹤連結統計
    tracked_link.click_count += 1

    # 4. 更新收件人狀態
    if r:
        recipient_result = await db.execute(
            select(CampaignRecipient).where(CampaignRecipient.id == r)
        )
        recipient = recipient_result.scalar_one_or_none()
        if recipient and not recipient.clicked:
            recipient.clicked = True
            recipient.clicked_at = datetime.now()

    await db.commit()

    # 5. 重新導向到原始 URL
    return RedirectResponse(url=tracked_link.original_url, status_code=302)
