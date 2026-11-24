import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import get_current_user
from app.db.supabase import supabase
from app.schemas.review import ReviewDueResponse
from datetime import datetime, timezone

from app.schemas.review import (
    ReviewDueResponse,
    ReviewSubmitRequest,
    ReviewSubmitResponse
)


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/reviews",
    tags=["Reviews"]
)


@router.get("/due", response_model=ReviewDueResponse)
def get_due_reviews(user=Depends(get_current_user)):
    user_id = str(user.id)

    today = datetime.now(
        ZoneInfo("Asia/Seoul")
    ).date().isoformat()

    try:
        # 1. 오늘까지 예정된 미완료 복습 일정 조회
        response = (
            supabase.table("review_schedules")
            .select("id, quiz_id, review_day, due_date")
            .eq("user_id", user_id)
            .lte("due_date", today)
            .is_("completed_at", "null")
            .order("due_date")
            .order("id")
            .execute()
        )

        schedules = response.data or []
        reviews = []

        # 2. 복습 일정에 해당하는 퀴즈 조회
        for schedule in schedules:
            quiz_response = (
                supabase.table("quizzes")
                .select("id, category_id, type, question")
                .eq("id", schedule["quiz_id"])
                .execute()
            )

            quizzes = quiz_response.data or []

            if not quizzes:
                continue

            quiz = quizzes[0]
            quiz["options"] = []

            # 3. 객관식 퀴즈라면 보기 조회
            if quiz["type"] == "multiple_choice":
                options_response = (
                    supabase.table("quiz_options")
                    .select("option_key, content")
                    .eq("quiz_id", quiz["id"])
                    .order("option_key")
                    .execute()
                )

                quiz["options"] = options_response.data or []

            # 4. 복습 목록에 추가
            reviews.append({
                "review_id": schedule["id"],
                "review_day": schedule["review_day"],
                "due_date": schedule["due_date"],
                "quiz": quiz
            })

        # 5. 복습 목록 반환
        return {
            "total": len(reviews),
            "reviews": reviews
        }

    except Exception:
        logger.exception("복습 대상 조회 중 오류 발생")

        raise HTTPException(
            status_code=500,
            detail="복습 대상 조회 중 오류가 발생했습니다."
        )

    
@router.post(
    "/{review_id}/submit",
    response_model=ReviewSubmitResponse,
    response_model_exclude_none=True
)
def submit_review(
    review_id: int,
    request: ReviewSubmitRequest,
    user=Depends(get_current_user)
):
    user_id = str(user.id)

    today = datetime.now(
        ZoneInfo("Asia/Seoul")
    ).date().isoformat()

    try:
        # 1. 사용자의 복습 일정 조회
        schedule_response = (
            supabase.table("review_schedules")
            .select("id, quiz_id, due_date, completed_at")
            .eq("id", review_id)
            .eq("user_id", user_id)
            .execute()
        )

        schedules = schedule_response.data or []

        if not schedules:
            raise HTTPException(
                status_code=404,
                detail="복습 일정을 찾을 수 없습니다."
            )

        schedule = schedules[0]
        quiz_id = schedule["quiz_id"]

        # 2. 이미 완료된 복습인지 확인
        if schedule["completed_at"] is not None:
            raise HTTPException(
                status_code=409,
                detail="이미 완료한 복습입니다."
            )

        # 3. 복습 예정일 확인
        if schedule["due_date"] > today:
            raise HTTPException(
                status_code=409,
                detail="아직 복습 예정일이 아닙니다."
            )

        # 4. 퀴즈 정보 조회
        quiz_response = (
            supabase.table("quizzes")
            .select(
                "id, type, correct_answer, "
                "explanation, retry_hint"
            )
            .eq("id", quiz_id)
            .execute()
        )

        quizzes = quiz_response.data or []

        if not quizzes:
            raise HTTPException(
                status_code=404,
                detail="퀴즈를 찾을 수 없습니다."
            )

        quiz = quizzes[0]

        # 5. 답안 형식 검증
        answer = request.answer.strip().upper()

        if quiz["type"] == "ox":
            allowed_answers = {"O", "X"}

        elif quiz["type"] == "multiple_choice":
            allowed_answers = {"A", "B", "C", "D"}

        else:
            raise HTTPException(
                status_code=400,
                detail="지원하지 않는 퀴즈 유형입니다."
            )

        if answer not in allowed_answers:
            raise HTTPException(
                status_code=422,
                detail="올바른 답안을 입력해 주세요."
            )

        # 6. 정답 여부 확인
        correct_answer = quiz["correct_answer"].strip().upper()
        is_correct = answer == correct_answer

        # 7. 복습 시도 기록 저장
        supabase.table("review_attempts").insert({
            "review_schedule_id": review_id,
            "selected_answer": answer,
            "is_correct": is_correct
        }).execute()

        # 8. 오답이면 재도전 힌트 반환
        if not is_correct:
            return {
                "review_id": review_id,
                "quiz_id": quiz_id,
                "is_correct": False,
                "status": "in_progress",
                "explanation": quiz["retry_hint"],
                "message": "해설을 확인하고 다시 풀어보세요."
            }

        # 9. 정답이면 복습 완료 처리
        completed_at = datetime.now(timezone.utc)

        update_response = (
            supabase.table("review_schedules")
            .update({
                "completed_at": completed_at.isoformat()
            })
            .eq("id", review_id)
            .eq("user_id", user_id)
            .is_("completed_at", "null")
            .execute()
        )

        if not update_response.data:
            raise HTTPException(
                status_code=409,
                detail="복습 진행 상태가 변경되었습니다."
            )

        # 10. 정답 결과 반환
        return {
            "review_id": review_id,
            "quiz_id": quiz_id,
            "is_correct": True,
            "status": "completed",
            "correct_answer": correct_answer,
            "explanation": quiz["explanation"],
            "message": "복습을 완료했습니다!"
        }

    except HTTPException:
        raise

    except Exception:
        logger.exception("복습 답안 제출 중 오류 발생")

        raise HTTPException(
            status_code=500,
            detail="복습 답안 제출 중 오류가 발생했습니다."
        )
