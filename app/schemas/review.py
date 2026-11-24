from datetime import date
from typing import Literal
from pydantic import BaseModel


# 객관식 퀴즈 보기
class ReviewOption(BaseModel):
    option_key: str
    content: str


# 복습 대상 퀴즈 정보
class ReviewQuiz(BaseModel):
    id: int
    category_id: int | None = None
    type: Literal["ox", "multiple_choice"]
    question: str
    options: list[ReviewOption] = []


# 개별 복습 일정 정보
class ReviewItem(BaseModel):
    review_id: int
    review_day: int
    due_date: date
    quiz: ReviewQuiz


# 복습 대상 조회 응답
class ReviewDueResponse(BaseModel):
    total: int
    reviews: list[ReviewItem]


# 복습 답안 제출 요청
class ReviewSubmitRequest(BaseModel):
    answer: str

 # 복습 답안 제출 응답
class ReviewSubmitResponse(BaseModel):
    review_id: int
    quiz_id: int
    is_correct: bool
    status: Literal["in_progress", "completed"]
    correct_answer: str | None = None
    explanation: str
    message: str