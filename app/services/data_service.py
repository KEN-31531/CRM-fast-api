import pandas as pd
from pathlib import Path
from datetime import datetime


class DataService:
    def __init__(self):
        self.base_path = Path(__file__).parent.parent.parent / "my_data"
        self.complete_course_path = self.base_path / "完整課程" / "聖誕節蛋糕製作完整課程名單.csv"
        self.experience_course_path = self.base_path / "體驗課程" / "聖誕節蛋糕製作體驗課程名單.csv"
        self._complete_df = None
        self._experience_df = None

    def _parse_date(self, date_str: str) -> datetime:
        return datetime.strptime(date_str, "%Y/%m/%d")

    def _parse_datetime(self, datetime_str: str) -> datetime:
        return datetime.strptime(datetime_str, "%Y/%m/%d %H:%M")

    def load_complete_course(self) -> pd.DataFrame:
        if self._complete_df is None:
            self._complete_df = pd.read_csv(self.complete_course_path, encoding="utf-8")
            self._complete_df["activity_type"] = "完整課程"
        return self._complete_df

    def load_experience_course(self) -> pd.DataFrame:
        if self._experience_df is None:
            self._experience_df = pd.read_csv(self.experience_course_path, encoding="utf-8")
            self._experience_df["activity_type"] = "體驗課程"
        return self._experience_df

    def get_all_participants(self) -> pd.DataFrame:
        complete_df = self.load_complete_course()
        experience_df = self.load_experience_course()
        return pd.concat([complete_df, experience_df], ignore_index=True)

    def get_customer_activities(self) -> list[dict]:
        all_data = self.get_all_participants()
        customers = {}

        for _, row in all_data.iterrows():
            phone = row["電話"]
            if phone not in customers:
                customers[phone] = {
                    "name": row["姓名"],
                    "phone": phone,
                    "birthday": row["生日"],
                    "complete_course_participations": [],
                    "experience_course_participations": [],
                    "purchased_from_complete": False,
                    "purchased_from_experience": False,
                }

            activity_time = row["參加活動時間"]
            purchased = row["是否購買課程"] == "是"

            if row["activity_type"] == "完整課程":
                customers[phone]["complete_course_participations"].append(activity_time)
                if purchased:
                    customers[phone]["purchased_from_complete"] = True
            else:
                customers[phone]["experience_course_participations"].append(activity_time)
                if purchased:
                    customers[phone]["purchased_from_experience"] = True

        return list(customers.values())

    def get_analysis(self) -> dict:
        complete_df = self.load_complete_course()
        experience_df = self.load_experience_course()

        complete_purchased = (complete_df["是否購買課程"] == "是").sum()
        experience_purchased = (experience_df["是否購買課程"] == "是").sum()

        complete_phones = set(complete_df["電話"].tolist())
        experience_phones = set(experience_df["電話"].tolist())

        both = complete_phones & experience_phones
        only_complete = complete_phones - experience_phones
        only_experience = experience_phones - complete_phones

        return {
            "total_complete_course_participants": len(complete_df),
            "total_experience_course_participants": len(experience_df),
            "complete_course_purchase_rate": round(complete_purchased / len(complete_df) * 100, 2) if len(complete_df) > 0 else 0,
            "experience_course_purchase_rate": round(experience_purchased / len(experience_df) * 100, 2) if len(experience_df) > 0 else 0,
            "complete_course_purchased_count": int(complete_purchased),
            "experience_course_purchased_count": int(experience_purchased),
            "customers_in_both": len(both),
            "customers_only_complete": len(only_complete),
            "customers_only_experience": len(only_experience),
            "customers_in_both_phones": list(both),
        }

    def get_conversion_analysis(self) -> dict:
        """分析體驗課程轉換為購買完整課程的關聯性"""
        complete_df = self.load_complete_course()
        experience_df = self.load_experience_course()

        # 取得參加體驗課程的顧客
        experience_phones = set(experience_df["電話"].tolist())

        # 取得購買完整課程的顧客
        complete_purchased_df = complete_df[complete_df["是否購買課程"] == "是"]
        complete_purchased_phones = set(complete_purchased_df["電話"].tolist())

        # 參加體驗課程後購買完整課程的顧客
        experience_to_complete = experience_phones & complete_purchased_phones

        # 只參加體驗課程就購買的顧客
        experience_purchased_df = experience_df[experience_df["是否購買課程"] == "是"]
        experience_only_purchased = set(experience_purchased_df["電話"].tolist()) - complete_purchased_phones

        return {
            "experience_participants": len(experience_phones),
            "experience_to_complete_purchase": len(experience_to_complete),
            "experience_to_complete_rate": round(len(experience_to_complete) / len(experience_phones) * 100, 2) if experience_phones else 0,
            "experience_only_purchased": len(experience_only_purchased),
            "experience_to_complete_customers": list(experience_to_complete),
        }


data_service = DataService()
