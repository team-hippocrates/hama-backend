from datetime import date
from pydantic import BaseModel


class AttendanceResponse(BaseModel):
    attended_today: bool
    total_attendance_days: int
    consecutive_attendance_days: int
    attendance_dates: list[date]