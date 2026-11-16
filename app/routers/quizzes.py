
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from app.core.security import get_current_user
from app.db.supabase import supabase

router = APIRouter(
    prefix="/api/v1/quizzes",
    tags=["Quizzes"]
)

@router.get("/next")
def get_next_quiz(
    # 퀴즈 유형 (ox: OX 문제, multiple_choice: 객관식 문제)
    # 기본값은 ox
    type: Literal["ox", "multiple_choice"] = Query(...),
    user=Depends(get_current_user)
):
    user_id = str(user.id)

    try:
        # 1. 사용자의 기존 퀴즈 진행 기록 조회
        progress_response = (
            supabase.table("user_quiz_progress")
            .select("quiz_id, status")
            .eq("user_id", user_id)
            .execute()
        )

        progress_list = progress_response.data or []

        # 2. 정답을 맞힌 문제와 진행 중인 문제 분류
        completed_ids = []
        in_progress_ids = []

        for progress in progress_list:
            if progress["status"] == "completed":
                completed_ids.append(progress["quiz_id"])
            elif progress["status"] == "in_progress":
                in_progress_ids.append(progress["quiz_id"])

        # 3. 검증된 퀴즈 조회
        quiz_response = (
            supabase.table("quizzes")
            .select("id, category_id, type, question")
            .eq("type", type)
            .eq("verification_status", "verified")
            .order("id")
            .execute()
        )

        quizzes = quiz_response.data or []

        selected_quiz = None

        # 4. 진행 중인 문제가 있다면 우선 선택
        for quiz in quizzes:
            if quiz["id"] in in_progress_ids:
                selected_quiz = quiz
                break

        # 5. 없다면 아직 완료하지 않은 문제 선택
        if selected_quiz is None:
            for quiz in quizzes:
                if quiz["id"] not in completed_ids:
                    selected_quiz = quiz
                    break

        if selected_quiz is None:
            raise HTTPException(
                status_code=404,
                detail="풀 수 있는 퀴즈가 없습니다."
            )

        # 6. 객관식 문제라면 보기 조회
        if type == "multiple_choice":
            options_response = (
                supabase.table("quiz_options")
                .select("option_key, content")
                .eq("quiz_id", selected_quiz["id"])
                .order("option_key")
                .execute()
            )

            selected_quiz["options"] = options_response.data or []

        return {"quiz": selected_quiz}

    except HTTPException:
        raise

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="퀴즈 조회 중 오류가 발생했습니다."
        )
