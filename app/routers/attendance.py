import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import get_current_user
from app.db.supabase import supabase
from app.schemas.attendance import AttendanceResponse


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/attendance",
    tags=["Attendance"]
)


@router.get("/me", response_model=AttendanceResponse)
def get_my_attendance(
    user=Depends(get_current_user)
):
    user_id = str(user.id)

    try:
        # 1. 한국 시간 기준 오늘 날짜
        today = datetime.now(
            ZoneInfo("Asia/Seoul")
        ).date()

        # 2. 사용자의 출석 기록 조회
        records = []
        page_size = 500
        offset = 0

        while True:
            response = (
                supabase.table("attendance")
                .select("attendance_date")
                .eq("user_id", user_id)
                .order("attendance_date")
                .range(offset, offset + page_size - 1)
                .execute()
            )

            batch = response.data or []
            records.extend(batch)

            if len(batch) < page_size:
                break

            offset += page_size

        # 3. 출석 날짜 변환
        attendance_dates = {
            date.fromisoformat(record["attendance_date"])
            for record in records
        }

        # 4. 오늘 출석 여부
        attended_today = today in attendance_dates

        # 5. 누적 출석 일수
        total_days = len(attendance_dates)

        # 6. 연속 출석 일수 계산
        consecutive_days = 0

        if attended_today:
            check_date = today
        else:
            check_date = today - timedelta(days=1)

        while check_date in attendance_dates:
            consecutive_days += 1
            check_date -= timedelta(days=1)

        # 7. 출석 현황 반환
        return AttendanceResponse(
            attended_today=attended_today,
            total_attendance_days=total_days,
            consecutive_attendance_days=consecutive_days,
            attendance_dates=sorted(attendance_dates)
        )

    except Exception:
        logger.exception("출석 기록 조회 중 오류 발생")

        raise HTTPException(
            status_code=500,
            detail="출석 기록 조회에 실패했습니다."
        )