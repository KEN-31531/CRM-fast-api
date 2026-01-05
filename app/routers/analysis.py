from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.services import db_service

router = APIRouter(prefix="/analysis", tags=["分析"])


@router.get("/summary")
async def get_summary_analysis(db: AsyncSession = Depends(get_db)):
    """取得整體分析摘要"""
    return await db_service.get_analysis(db)


@router.get("/conversion")
async def get_conversion_analysis(db: AsyncSession = Depends(get_db)):
    """分析體驗課程到購買完整課程的轉換率"""
    return await db_service.get_conversion_analysis(db)


@router.get("/activity-correlation")
async def get_activity_correlation(db: AsyncSession = Depends(get_db)):
    """分析活動參與與購買課程的關聯性"""
    analysis = await db_service.get_analysis(db)
    conversion = await db_service.get_conversion_analysis(db)

    return {
        "summary": {
            "完整課程": {
                "參與人數": analysis["total_complete_course_participants"],
                "購買人數": analysis["complete_course_purchased_count"],
                "購買率": f"{analysis['complete_course_purchase_rate']}%",
            },
            "體驗課程": {
                "參與人數": analysis["total_experience_course_participants"],
                "購買人數": analysis["experience_course_purchased_count"],
                "購買率": f"{analysis['experience_course_purchase_rate']}%",
            },
        },
        "customer_overlap": {
            "同時參加兩種課程的顧客數": analysis["customers_in_both"],
            "只參加完整課程的顧客數": analysis["customers_only_complete"],
            "只參加體驗課程的顧客數": analysis["customers_only_experience"],
        },
        "conversion_funnel": {
            "體驗課程參與者": conversion["experience_participants"],
            "體驗後購買完整課程人數": conversion["experience_to_complete_purchase"],
            "轉換率": f"{conversion['experience_to_complete_rate']}%",
        },
        "insights": _generate_insights(analysis, conversion),
    }


def _generate_insights(analysis: dict, conversion: dict) -> list[str]:
    """根據數據生成洞察"""
    insights = []

    if analysis["complete_course_purchase_rate"] > analysis["experience_course_purchase_rate"]:
        insights.append(
            f"完整課程的購買率 ({analysis['complete_course_purchase_rate']}%) "
            f"高於體驗課程 ({analysis['experience_course_purchase_rate']}%)"
        )
    else:
        insights.append(
            f"體驗課程的購買率 ({analysis['experience_course_purchase_rate']}%) "
            f"高於完整課程 ({analysis['complete_course_purchase_rate']}%)"
        )

    if analysis["customers_in_both"] > 0:
        insights.append(
            f"有 {analysis['customers_in_both']} 位顧客同時參加了完整課程和體驗課程"
        )

    if conversion["experience_to_complete_rate"] > 0:
        insights.append(
            f"體驗課程到完整課程的轉換率為 {conversion['experience_to_complete_rate']}%"
        )

    return insights
