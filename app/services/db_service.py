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

    async def import_customers_smart(
        self,
        db: AsyncSession,
        csv_content: str,
        course_info: dict | None = None
    ) -> dict:
        """智慧匯入顧客資料（自動識別欄位）"""
        import io

        # 解析 CSV
        df = pd.read_csv(io.StringIO(csv_content), encoding="utf-8", dtype={"電話": str})

        # 欄位名稱對應（支援多種寫法）
        column_mapping = {
            "姓名": ["姓名", "名字", "name", "Name"],
            "電話": ["電話", "手機", "phone", "Phone", "tel", "Tel"],
            "Email": ["Email", "email", "EMAIL", "信箱", "電子郵件"],
            "生日": ["生日", "birthday", "Birthday", "出生日期"],
            "參加活動時間": ["參加活動時間", "活動時間", "時間", "date", "Date"],
            "是否購買課程": ["是否購買課程", "購買", "是否購買", "purchased"],
            "課程名稱": ["課程名稱", "課程", "course", "Course"],
            "課程類型": ["課程類型", "類型", "type", "Type"],
        }

        # 找到實際欄位名稱
        def find_column(target):
            for possible_name in column_mapping.get(target, [target]):
                if possible_name in df.columns:
                    return possible_name
            return None

        # 建立欄位對應
        col_name = find_column("姓名")
        col_phone = find_column("電話")
        col_email = find_column("Email")
        col_birthday = find_column("生日")
        col_activity_time = find_column("參加活動時間")
        col_purchased = find_column("是否購買課程")
        col_course_name = find_column("課程名稱")
        col_course_type = find_column("課程類型")

        if not col_name or not col_phone:
            return {
                "success": False,
                "message": "CSV 必須包含「姓名」和「電話」欄位",
                "imported": 0,
                "updated": 0
            }

        imported_count = 0
        updated_count = 0
        participation_count = 0
        errors = []

        # 課程快取
        course_cache = {}

        # 決定課程資訊來源
        has_course_columns = col_course_name and col_course_type
        use_filename_course = course_info and not has_course_columns

        for idx, row in df.iterrows():
            try:
                phone = str(row[col_phone]).zfill(10)

                # 檢查顧客是否已存在
                result = await db.execute(
                    select(Customer).where(Customer.phone == phone)
                )
                customer = result.scalar_one_or_none()

                if not customer:
                    email_val = row.get(col_email, "") if col_email and pd.notna(row.get(col_email)) else ""
                    birthday_val = self._parse_date(row[col_birthday]) if col_birthday and pd.notna(row.get(col_birthday)) else None

                    customer = Customer(
                        name=row[col_name],
                        phone=phone,
                        email=email_val,
                        birthday=birthday_val,
                    )
                    db.add(customer)
                    await db.flush()
                    imported_count += 1
                else:
                    if col_email and pd.notna(row.get(col_email)) and row.get(col_email):
                        customer.email = row[col_email]
                    if col_birthday and pd.notna(row.get(col_birthday)) and row.get(col_birthday):
                        customer.birthday = self._parse_date(row[col_birthday])
                    updated_count += 1

                # 處理課程參與記錄
                course_name = None
                course_type = None

                if has_course_columns:
                    course_name = row.get(col_course_name) if pd.notna(row.get(col_course_name)) else None
                    course_type = row.get(col_course_type) if pd.notna(row.get(col_course_type)) else None
                elif use_filename_course:
                    course_name = course_info.get("name")
                    course_type = course_info.get("type")

                if course_name and course_type:
                    cache_key = f"{course_name}_{course_type}"

                    if cache_key not in course_cache:
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

                        course_cache[cache_key] = course
                    else:
                        course = course_cache[cache_key]

                    # 取得活動時間
                    activity_time = None
                    if col_activity_time and pd.notna(row.get(col_activity_time)):
                        activity_time = self._parse_datetime(row[col_activity_time])

                    if activity_time:
                        result = await db.execute(
                            select(ActivityParticipation).where(
                                ActivityParticipation.customer_id == customer.id,
                                ActivityParticipation.course_id == course.id,
                                ActivityParticipation.activity_time == activity_time
                            )
                        )
                        existing = result.scalar_one_or_none()

                        if not existing:
                            purchased = False
                            if col_purchased and pd.notna(row.get(col_purchased)):
                                purchased = row[col_purchased] in ["是", "yes", "Yes", "YES", "1", True]

                            participation = ActivityParticipation(
                                customer_id=customer.id,
                                course_id=course.id,
                                activity_time=activity_time,
                                purchased=purchased,
                            )
                            db.add(participation)
                            participation_count += 1

            except Exception as e:
                errors.append(f"第 {idx + 2} 行錯誤: {str(e)}")

        await db.commit()

        message = f"匯入完成：新增 {imported_count} 位顧客，更新 {updated_count} 位顧客"
        if participation_count > 0:
            message += f"，新增 {participation_count} 筆課程參與記錄"
        if use_filename_course:
            message += f"（課程：{course_info['name']} - {course_info['type']}）"

        return {
            "success": True,
            "message": message,
            "imported": imported_count,
            "updated": updated_count,
            "participations": participation_count,
            "errors": errors if errors else None
        }

    async def import_customers_only(
        self,
        db: AsyncSession,
        csv_content: str
    ) -> dict:
        """從 CSV 匯入顧客資料（自動識別格式）"""
        import io

        # 解析 CSV
        df = pd.read_csv(io.StringIO(csv_content), encoding="utf-8", dtype={"電話": str})

        # 檢查是否包含課程相關欄位
        has_course_info = all(col in df.columns for col in ["課程名稱", "課程類型", "參加活動時間", "是否購買課程"])

        imported_count = 0
        updated_count = 0
        participation_count = 0
        errors = []

        # 課程快取
        course_cache = {}

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
                        email=row.get("Email", "") if pd.notna(row.get("Email")) else "",
                        birthday=self._parse_date(row["生日"]) if pd.notna(row.get("生日")) else None,
                    )
                    db.add(customer)
                    await db.flush()
                    imported_count += 1
                else:
                    # 更新現有顧客資料
                    if pd.notna(row.get("Email")) and row.get("Email"):
                        customer.email = row["Email"]
                    if pd.notna(row.get("生日")) and row.get("生日"):
                        customer.birthday = self._parse_date(row["生日"])
                    updated_count += 1

                # 如果有課程資訊，建立課程參與記錄
                if has_course_info and pd.notna(row.get("課程名稱")) and pd.notna(row.get("課程類型")):
                    course_name = row["課程名稱"]
                    course_type = row["課程類型"]
                    cache_key = f"{course_name}_{course_type}"

                    # 從快取或資料庫取得課程
                    if cache_key not in course_cache:
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

                        course_cache[cache_key] = course
                    else:
                        course = course_cache[cache_key]

                    # 檢查是否已有該課程的參與記錄
                    activity_time = self._parse_datetime(row["參加活動時間"]) if pd.notna(row.get("參加活動時間")) else None

                    if activity_time:
                        result = await db.execute(
                            select(ActivityParticipation).where(
                                ActivityParticipation.customer_id == customer.id,
                                ActivityParticipation.course_id == course.id,
                                ActivityParticipation.activity_time == activity_time
                            )
                        )
                        existing = result.scalar_one_or_none()

                        if not existing:
                            participation = ActivityParticipation(
                                customer_id=customer.id,
                                course_id=course.id,
                                activity_time=activity_time,
                                purchased=row["是否購買課程"] == "是" if pd.notna(row.get("是否購買課程")) else False,
                            )
                            db.add(participation)
                            participation_count += 1

            except Exception as e:
                errors.append(f"第 {idx + 2} 行錯誤: {str(e)}")

        await db.commit()

        message = f"匯入完成：新增 {imported_count} 位顧客，更新 {updated_count} 位顧客"
        if has_course_info:
            message += f"，新增 {participation_count} 筆課程參與記錄"

        return {
            "success": True,
            "message": message,
            "imported": imported_count,
            "updated": updated_count,
            "participations": participation_count if has_course_info else 0,
            "errors": errors if errors else None
        }

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
                "created_at": customer.created_at.isoformat() if customer.created_at else "",
                "complete_course_participations": [
                    {"activity_time": t.isoformat() if t else ""} for t in complete_times
                ],
                "experience_course_participations": [
                    {"activity_time": t.isoformat() if t else ""} for t in experience_times
                ],
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
