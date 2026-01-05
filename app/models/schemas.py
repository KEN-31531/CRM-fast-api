from pydantic import BaseModel
from datetime import date, datetime


class CustomerCreate(BaseModel):
    name: str
    phone: str
    birthday: date


class CustomerResponse(BaseModel):
    id: int
    name: str
    phone: str
    birthday: date

    class Config:
        from_attributes = True


class CourseResponse(BaseModel):
    id: int
    name: str
    course_type: str

    class Config:
        from_attributes = True


class ParticipationResponse(BaseModel):
    id: int
    customer_id: int
    course_id: int
    activity_time: datetime
    purchased: bool

    class Config:
        from_attributes = True


class CustomerActivity(BaseModel):
    id: int
    name: str
    phone: str
    birthday: date
    complete_course_participations: list[datetime]
    experience_course_participations: list[datetime]
    purchased_from_complete: bool
    purchased_from_experience: bool


class AnalysisResult(BaseModel):
    total_complete_course_participants: int
    total_experience_course_participants: int
    complete_course_purchase_rate: float
    experience_course_purchase_rate: float
    customers_in_both: int
    customers_only_complete: int
    customers_only_experience: int
