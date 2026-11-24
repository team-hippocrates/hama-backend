
import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from app.core.security import get_current_user
from app.db.supabase import supabase
from pydantic import BaseModel
from datetime import datetime, timezone
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/quizzes",
    tags=["Quizzes"]
)
def record_attendance(user_id: str):
    # 한국 시간 기준 오늘 날짜
    today = datetime.now(
        ZoneInfo("Asia/Seoul")
    ).date().isoformat()

    # 출석 기록 저장
    supabase.table("attendance").upsert(
        {
            "user_id": user_id,
            "attendance_date": today
        },
        on_conflict="user_id,attendance_date",
        ignore_duplicates=True
    ).execute()

@router.get("/next")
def get_next_quiz(
    type: Literal["ox", "multiple_choice"] = Query("ox"),
    user=Depends(get_current_user)
):
    user_id = str(user.id)

    try:
        # 1. 사용자의 모든 퀴즈 진행 기록 조회
        progress_response = (
            supabase.table("user_quiz_progress")
            .select("quiz_id, status")
            .eq("user_id", user_id)
            .execute()
        )

        progress_list = progress_response.data or []

        completed_ids = set()
        active_quiz_id = None

        for progress in progress_list:
            if progress["status"] == "completed":
                completed_ids.add(progress["quiz_id"])

            elif progress["status"] == "in_progress":
                active_quiz_id = progress["quiz_id"]

        # 2. 이미 진행 중인 문제가 있다면 먼저 확인
        if active_quiz_id is not None:
            active_response = (
                supabase.table("quizzes")
                .select("id, category_id, type, question")
                .eq("id", active_quiz_id)
                .execute()
            )

            active_quizzes = active_response.data or []

            if not active_quizzes:
                raise HTTPException(
                    status_code=409,
                    detail="진행 중인 퀴즈 정보를 찾을 수 없습니다."
                )

            active_quiz = active_quizzes[0]

            # 다른 유형의 퀴즈는 시작할 수 없음
            if active_quiz["type"] != type:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "message": "진행 중인 퀴즈를 먼저 완료해 주세요.",
                        "active_quiz_id": active_quiz_id,
                        "active_quiz_type": active_quiz["type"]
                    }
                )

            selected_quiz = active_quiz

        else:
            # 3. 진행 중인 문제가 없으면 새로운 퀴즈 선택
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

            for quiz in quizzes:
                if quiz["id"] not in completed_ids:
                    selected_quiz = quiz
                    break

            if selected_quiz is None:
                raise HTTPException(
                    status_code=404,
                    detail="풀 수 있는 퀴즈가 없습니다."
                )

            # 4. 새 퀴즈의 진행 기록 저장
            supabase.table("user_quiz_progress").insert({
                "user_id": user_id,
                "quiz_id": selected_quiz["id"],
                "status": "in_progress"
            }).execute()

        # 5. 객관식 문제라면 보기 조회
        if selected_quiz["type"] == "multiple_choice":
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
        logger.exception("퀴즈 조회 중 오류 발생")
        raise HTTPException(
            status_code=500,
            detail="퀴즈 조회 중 오류가 발생했습니다."
        )


# 정답 제출 요청 데이터
class QuizSubmitRequest(BaseModel):
    answer: str


@router.post("/{quiz_id}/submit")
def submit_quiz(
    quiz_id: int,
    request: QuizSubmitRequest,
    user=Depends(get_current_user)
):
    user_id = str(user.id)

    try:
        # 1. 퀴즈 조회
        quiz_response = (
            supabase.table("quizzes")
            .select("id, type, correct_answer, explanation, retry_hint")
            .eq("id", quiz_id)
            .execute()
        )

        quizzes = quiz_response.data or []

        if not quizzes:
            raise HTTPException(
                status_code=404,
                detail="존재하지 않는 퀴즈입니다."
            )

        quiz = quizzes[0]

        # 2. 현재 사용자의 해당 퀴즈 진행 기록 조회
        progress_response = (
            supabase.table("user_quiz_progress")
            .select("status")
            .eq("user_id", user_id)
            .eq("quiz_id", quiz_id)
            .execute()
        )

        progress_list = progress_response.data or []

        if not progress_list:
            raise HTTPException(
                status_code=409,
                detail="먼저 퀴즈를 조회해 주세요."
            )

        if progress_list[0]["status"] == "completed":
            raise HTTPException(
                status_code=409,
                detail="이미 완료한 퀴즈입니다."
            )

        if progress_list[0]["status"] != "in_progress":
            raise HTTPException(
                status_code=409,
                detail="진행 중인 퀴즈가 아닙니다."
            )

        # 3. 답안 형식 검증
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

        # 4. 정답 확인
        correct_answer = quiz["correct_answer"].strip().upper()
        is_correct = answer == correct_answer

        # 5. 오답이면 진행 상태 유지
        if not is_correct:
            return {
                "quiz_id": quiz_id,
                "is_correct": False,
                "status": "in_progress",
                "explanation": quiz["explanation"],
                "message": "해설을 확인하고 다시 풀어보세요."
            }

        # 6. 정답이면 완료 상태로 변경
        update_response = (
            supabase.table("user_quiz_progress")
            .update({
                "status": "completed",
               "first_correct_at": datetime.now(timezone.utc).isoformat()
            })
            .eq("user_id", user_id)
            .eq("quiz_id", quiz_id)
            .eq("status", "in_progress")
            .execute()
        )

        if not update_response.data:
            raise HTTPException(
                status_code=409,
                detail="퀴즈 진행 상태가 변경되었습니다."
            )
            # 7. 정답을 맞혔으므로 당일 출석 기록
        record_attendance(user_id)

        # 7. 정답 결과 반환
        return {
            "quiz_id": quiz_id,
            "is_correct": True,
            "status": "completed",
            "correct_answer": correct_answer,
            "explanation": quiz["explanation"],
            "message": "정답입니다!"
        }

    except HTTPException:
        raise

    except Exception:
        logger.exception("퀴즈 정답 제출 중 오류 발생")
        raise HTTPException(
            status_code=500,
            detail="퀴즈 정답 제출 중 오류가 발생했습니다."
        )



# 퀴즈 유형 조회
@router.get("/types")
def get_quiz_types():
    return {
        "types": [
            {
                "type": "ox",
                "name": "OX 퀴즈"
            },
            {
                "type": "multiple_choice",
                "name": "객관식 퀴즈"
            }
        ]
    }