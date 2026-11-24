from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.db.supabase import supabase


REVIEW_DAYS = [0, 3, 7, 14, 30] # 복습 주기


def create_review_schedules(
    user_id: str,
    quiz_id: int,
    first_correct_at: datetime
):
    # 1. 최초 학습 완료일을 한국 시간 기준으로 변환
    learning_date = first_correct_at.astimezone(
        ZoneInfo("Asia/Seoul")
    ).date()

    # 2. 복습 일정 생성
    schedules = []

    for review_day in REVIEW_DAYS:
        due_date = learning_date + timedelta(days=review_day)

        schedules.append({
            "user_id": user_id,
            "quiz_id": quiz_id,
            "review_day": review_day,
            "due_date": due_date.isoformat()
        })

    # 3. Supabase에 복습 일정 저장
    response = supabase.table("review_schedules").upsert(
        schedules,
        on_conflict="user_id,quiz_id,review_day",
        ignore_duplicates=True
    ).execute()

    print("복습 일정 저장 결과:", response.data)