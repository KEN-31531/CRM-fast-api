from sqlalchemy import String, Date, DateTime, Boolean, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import date, datetime
from app.database import Base


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True)
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
