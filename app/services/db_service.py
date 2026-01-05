import pandas as pd
from pathlib import Path
from datetime import datetime
from sqlalchemy import select, func, Integer
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.db_models import Customer, Course, ActivityParticipation


class DatabaseService:
    def __init__(self):
        self.base_path = Path(__file__).parent.parent.parent / "my_data"
        self.complete_course_path = self.base_path / "完整課程" / "聖誕節蛋糕製作完整課程名單.csv"
        self.experience_course_path = self.base_path / "體驗課程" / "聖誕節蛋糕製作體驗課程名單.csv"

    def _parse_date(self, date_str: str):
        return datetime.strptime(date_str, "%Y/%m/%d").date()

    def _parse_datetime(self, datetime_str: str):
        return datetime.strptime(datetime_str, "%Y/%m/%d %H:%M")

    def _mask_email(self, email: str) -> str:
        """遮蔽 Email，只顯示首字母和域名"""
        if not email or "@" not in email:
            return email
        local, domain = email.split("@", 1)
        if len(local) <= 1:
            masked_local = local
        else:
            masked_local = local[0] + "***"
        return f"{masked_local}@{domain}"

    async def import_csv_data(self, db: AsyncSession):
        """從 CSV 匯入資料到資料庫"""
        # 建立課程
        complete_course = Course(name="聖誕節蛋糕製作完整課程", course_type="完整課程")
        experience_course = Course(name="聖誕節蛋糕製作體驗課程", course_type="體驗課程")
        db.add_all([complete_course, experience_course])
        await db.flush()

        # 匯入完整課程資料
        await self._import_course_csv(db, self.complete_course_path, complete_course.id)

        # 匯入體驗課程資料
        await self._import_course_csv(db, self.experience_course_path, experience_course.id)

        await db.commit()
        return {"message": "資料匯入成功"}

    async def import_customers_from_csv(
        self,
        db: AsyncSession,
        csv_content: str,
        course_name: str,
        course_type: str
    ) -> dict:
        """從上傳的 CSV 內容匯入顧客資料"""
        import io

        # 檢查或建立課程
        result = await db.execute(
            select(Course).where(
                Course.name == course_name,
                Course.course_type == course_type
            )
        )
        course = result.scalar_one_or_none()

        if not course:
            course = Course(name=course_name, course_type=course_type)
            db.add(course)
            await db.flush()

        # 解析 CSV
        df = pd.read_csv(io.StringIO(csv_content), encoding="utf-8", dtype={"電話": str})

        imported_count = 0
        updated_count = 0
        errors = []

        for idx, row in df.iterrows():
            try:
                phone = str(row["電話"]).zfill(10)

                # 檢查顧客是否已存在
                result = await db.execute(
                    select(Customer).where(Customer.phone == phone)
                )
                customer = result.scalar_one_or_none()

                if not customer:
                    customer = Customer(
                        name=row["姓名"],
                        phone=phone,
                        email=row.get("Email", ""),
                        birthday=self._parse_date(row["生日"]),
                    )
                    db.add(customer)
                    await db.flush()
                    imported_count += 1
                else:
                    updated_count += 1

                # 檢查是否已有該課程的參與記錄
                result = await db.execute(
                    select(ActivityParticipation).where(
                        ActivityParticipation.customer_id == customer.id,
                        ActivityParticipation.course_id == course.id,
                        ActivityParticipation.activity_time == self._parse_datetime(row["參加活動時間"])
                    )
                )
                existing = result.scalar_one_or_none()

                if not existing:
                    participation = ActivityParticipation(
                        customer_id=customer.id,
                        course_id=course.id,
                        activity_time=self._parse_datetime(row["參加活動時間"]),
                        purchased=row["是否購買課程"] == "是",
                    )
                    db.add(participation)

            except Exception as e:
                errors.append(f"第 {idx + 2} 行錯誤: {str(e)}")

        await db.commit()

        return {
            "success": True,
            "message": f"匯入完成：新增 {imported_count} 位顧客，更新 {updated_count} 位顧客",
            "imported": imported_count,
            "updated": updated_count,
            "errors": errors if errors else None
        }

    async def _import_course_csv(self, db: AsyncSession, csv_path: Path, course_id: int):
        df = pd.read_csv(csv_path, encoding="utf-8", dtype={"電話": str})

        for _, row in df.iterrows():
            phone = str(row["電話"]).zfill(10)  # 確保電話號碼為字串且補足前導零

            # 檢查顧客是否已存在
            result = await db.execute(
                select(Customer).where(Customer.phone == phone)
            )
            customer = result.scalar_one_or_none()

            if not customer:
                customer = Customer(
                    name=row["姓名"],
                    phone=phone,
                    email=row.get("Email", ""),
                    birthday=self._parse_date(row["生日"]),
                )
                db.add(customer)
                await db.flush()

            # 建立活動參與記錄
            participation = ActivityParticipation(
                customer_id=customer.id,
                course_id=course_id,
                activity_time=self._parse_datetime(row["參加活動時間"]),
                purchased=row["是否購買課程"] == "是",
            )
            db.add(participation)

    async def get_all_customers(self, db: AsyncSession) -> list[Customer]:
        result = await db.execute(select(Customer))
        return result.scalars().all()

    async def get_customer_by_phone(self, db: AsyncSession, phone: str) -> Customer | None:
        result = await db.execute(
            select(Customer).where(Customer.phone == phone)
        )
        return result.scalar_one_or_none()

    async def get_all_courses(self, db: AsyncSession) -> list[Course]:
        result = await db.execute(select(Course))
        return result.scalars().all()

    async def get_participations_by_course_type(
        self, db: AsyncSession, course_type: str
    ) -> list[ActivityParticipation]:
        result = await db.execute(
            select(ActivityParticipation)
            .join(Course)
            .where(Course.course_type == course_type)
        )
        return result.scalars().all()

    async def get_customer_activities(self, db: AsyncSession) -> list[dict]:
        customers = await self.get_all_customers(db)
        result = []

        for customer in customers:
            # 取得該顧客的所有參與記錄
            participations_result = await db.execute(
                select(ActivityParticipation, Course)
                .join(Course)
                .where(ActivityParticipation.customer_id == customer.id)
            )
            participations = participations_result.all()

            complete_times = []
            experience_times = []
            purchased_complete = False
            purchased_experience = False

            for participation, course in participations:
                if course.course_type == "完整課程":
                    complete_times.append(participation.activity_time)
                    if participation.purchased:
                        purchased_complete = True
                else:
                    experience_times.append(participation.activity_time)
                    if participation.purchased:
                        purchased_experience = True

            result.append({
                "id": customer.id,
                "name": customer.name,
                "phone": customer.phone,
                "email": self._mask_email(customer.email) if customer.email else "",
                "birthday": customer.birthday,
                "complete_course_participations": complete_times,
                "experience_course_participations": experience_times,
                "purchased_from_complete": purchased_complete,
                "purchased_from_experience": purchased_experience,
            })

        return result

    async def get_analysis(self, db: AsyncSession) -> dict:
        # 完整課程統計
        complete_result = await db.execute(
            select(
                func.count(ActivityParticipation.id),
                func.sum(func.cast(ActivityParticipation.purchased, Integer))
            )
            .join(Course)
            .where(Course.course_type == "完整課程")
        )
        complete_count, complete_purchased = complete_result.one()
        complete_purchased = complete_purchased or 0

        # 體驗課程統計
        experience_result = await db.execute(
            select(
                func.count(ActivityParticipation.id),
                func.sum(func.cast(ActivityParticipation.purchased, Integer))
            )
            .join(Course)
            .where(Course.course_type == "體驗課程")
        )
        experience_count, experience_purchased = experience_result.one()
        experience_purchased = experience_purchased or 0

        # 顧客重疊分析
        complete_customers = await db.execute(
            select(Customer.phone)
            .join(ActivityParticipation)
            .join(Course)
            .where(Course.course_type == "完整課程")
            .distinct()
        )
        complete_phones = set(row[0] for row in complete_customers)

        experience_customers = await db.execute(
            select(Customer.phone)
            .join(ActivityParticipation)
            .join(Course)
            .where(Course.course_type == "體驗課程")
            .distinct()
        )
        experience_phones = set(row[0] for row in experience_customers)

        both = complete_phones & experience_phones
        only_complete = complete_phones - experience_phones
        only_experience = experience_phones - complete_phones

        return {
            "total_complete_course_participants": complete_count,
            "total_experience_course_participants": experience_count,
            "complete_course_purchase_rate": round(complete_purchased / complete_count * 100, 2) if complete_count else 0,
            "experience_course_purchase_rate": round(experience_purchased / experience_count * 100, 2) if experience_count else 0,
            "complete_course_purchased_count": int(complete_purchased),
            "experience_course_purchased_count": int(experience_purchased),
            "customers_in_both": len(both),
            "customers_only_complete": len(only_complete),
            "customers_only_experience": len(only_experience),
        }

    async def get_conversion_analysis(self, db: AsyncSession) -> dict:
        """分析體驗課程轉換為購買完整課程的關聯性"""
        # 參加體驗課程的顧客
        experience_customers = await db.execute(
            select(Customer.phone)
            .join(ActivityParticipation)
            .join(Course)
            .where(Course.course_type == "體驗課程")
            .distinct()
        )
        experience_phones = set(row[0] for row in experience_customers)

        # 購買完整課程的顧客
        complete_purchased = await db.execute(
            select(Customer.phone)
            .join(ActivityParticipation)
            .join(Course)
            .where(Course.course_type == "完整課程")
            .where(ActivityParticipation.purchased == True)
            .distinct()
        )
        complete_purchased_phones = set(row[0] for row in complete_purchased)

        # 體驗後購買完整課程
        experience_to_complete = experience_phones & complete_purchased_phones

        # 只在體驗課程購買
        experience_only_purchased = await db.execute(
            select(Customer.phone)
            .join(ActivityParticipation)
            .join(Course)
            .where(Course.course_type == "體驗課程")
            .where(ActivityParticipation.purchased == True)
            .distinct()
        )
        experience_only_purchased_phones = set(row[0] for row in experience_only_purchased) - complete_purchased_phones

        return {
            "experience_participants": len(experience_phones),
            "experience_to_complete_purchase": len(experience_to_complete),
            "experience_to_complete_rate": round(len(experience_to_complete) / len(experience_phones) * 100, 2) if experience_phones else 0,
            "experience_only_purchased": len(experience_only_purchased_phones),
        }


db_service = DatabaseService()
