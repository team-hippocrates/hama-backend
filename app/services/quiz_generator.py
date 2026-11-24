
import argparse
import logging
import os
import re
import time

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from app.db.supabase import supabase

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

TOPICS = ["역사", "문화", "일반상식", "직장생활 예의"]
DIFFICULTIES = ["easy", "medium", "hard"]
QUIZ_TYPES = ["ox", "multiple_choice"]


# 1. Gemini 응답 데이터 구조
class QuizOption(BaseModel):
    option_key: str
    content: str = Field(min_length=1)


class GeneratedQuiz(BaseModel):
    question: str = Field(min_length=5)
    correct_answer: str
    explanation: str = Field(min_length=10)
    retry_hint: str = Field(min_length=3)
    options: list[QuizOption] = Field(default_factory=list)


class QuizBatch(BaseModel):
    quizzes: list[GeneratedQuiz]


# 2. 문제 형식 검사
def validate_quiz(quiz, quiz_type):
    answer = quiz.correct_answer.strip().upper()

    if quiz_type == "ox":
        if answer not in ("O", "X"):
            raise ValueError("OX 정답은 O 또는 X여야 합니다.")

        if quiz.options:
            raise ValueError("OX 문제에 선택지가 있습니다.")

    elif quiz_type == "multiple_choice":
        if answer not in ("A", "B", "C", "D"):
            raise ValueError("객관식 정답 형식 오류")

        keys = [o.option_key for o in quiz.options]

        if sorted(keys) != ["A", "B", "C", "D"]:
            raise ValueError("객관식 선택지는 A~D가 필요합니다.")

        contents = [o.content.strip() for o in quiz.options]

        if len(set(contents)) != 4:
            raise ValueError("중복 선택지가 있습니다.")

    if quiz.explanation.strip() == quiz.retry_hint.strip():
        raise ValueError("해설과 힌트가 동일합니다.")


# 3. Gemini 문제 생성
def generate_batch(client, topic, difficulty, quiz_type, count):
    difficulty_ko = {
        "easy": "하",
        "medium": "중",
        "hard": "상",
    }[difficulty]

    prompt = f"""
너는 한국 고등학생을 위한 교육용 퀴즈 출제자다.

주제: {topic}
난이도: {difficulty_ko}
유형: {quiz_type}
생성 수: {count}개

[출제 규칙]
- 모든 문항은 한국어로 작성한다.
- 사실관계가 명확한 문제만 만든다.
- 한 배치 내에서 동일한 지식을 반복해서 묻지 않는다.
- OX 문제는 정답을 O 또는 X로 표시한다.
- 객관식 문제는 A, B, C, D 보기 4개를 만든다.
- 객관식에는 정답이 정확히 하나만 있어야 한다.
- OX 문제의 options는 빈 배열로 작성한다.
- 난이도에 맞는 어휘와 사고 수준을 사용한다.

[해설 규칙]
explanation은 틀린 학생에게 보여줄 개념 설명이다.
정답을 직접 말하거나 정답을 확정할 수 있는
결정적 표현을 사용하지 않는다.
객관식 정답의 보기 문구를 그대로 반복하지 않는다.
OX의 참/거짓을 직접 공개하지 않는다.
문제 해결에 필요한 배경지식과 판단 기준을 설명한다.

retry_hint는 explanation보다 짧은 힌트다.
정답을 직접 공개하지 않는다.

정확히 {count}개를 생성하라.
"""

    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=QuizBatch,
            temperature=0.5,
        ),
    )

    if not response.text:
        raise RuntimeError("Gemini가 빈 응답을 반환했습니다.")

    batch = QuizBatch.model_validate_json(response.text)

    if len(batch.quizzes) != count:
        raise ValueError(
            f"문제 개수 오류: {len(batch.quizzes)}/{count}"
        )

    for quiz in batch.quizzes:
        validate_quiz(quiz, quiz_type)

    return batch.quizzes


# 4. Google Search 기반 출처 검증
def verify_quiz(client, quiz, topic, quiz_type):
    options_text = "\n".join(
        f"{o.option_key}. {o.content}"
        for o in quiz.options
    )

    prompt = f"""
다음 교육용 문제를 신뢰할 수 있는 자료로 검증하라.

주제: {topic}
유형: {quiz_type}
문제: {quiz.question}
선택지:
{options_text}

제시된 정답: {quiz.correct_answer}
오답용 개념 설명: {quiz.explanation}

Google Search를 사용하여 관련 근거를 확인하라.

다음 형식으로 간결하게 답하라.

SUPPORTED: YES 또는 NO
ANSWER_CORRECT: YES 또는 NO
EXPLANATION_SAFE: YES 또는 NO
EVIDENCE: 정답을 뒷받침하는 구체적 사실
REASON: 검증 이유

규칙:
- 검색 근거가 불충분하면 SUPPORTED: NO
- 정답이 틀렸거나 애매하면 ANSWER_CORRECT: NO
- 오답용 설명이 정답을 직접 알려주거나
  사실상 정답을 확정하면 EXPLANATION_SAFE: NO
- 추측하지 말 것
"""

    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[
                types.Tool(
                    google_search=types.GoogleSearch()
                )
            ],
            temperature=0,
        ),
    )

    result_text = response.text or ""

    sources = []
    metadata = None

    if response.candidates:
        metadata = response.candidates[0].grounding_metadata

    if metadata and metadata.grounding_chunks:
        for chunk in metadata.grounding_chunks:
            if chunk.web and chunk.web.uri:
                uri = chunk.web.uri
                title = chunk.web.title or "검색 출처"

                if uri not in [s["url"] for s in sources]:
                    sources.append({
                        "title": title,
                        "url": uri,
                    })

    def flag(name):
        match = re.search(
            rf"^{name}:\s*(YES|NO)\s*$",
            result_text,
            re.MULTILINE | re.IGNORECASE,
        )
        return bool(
            match and match.group(1).upper() == "YES"
        )

    passed = (
        flag("SUPPORTED")
        and flag("ANSWER_CORRECT")
        and flag("EXPLANATION_SAFE")
        and len(sources) > 0
    )

    return {
        "passed": passed,
        "sources": sources,
        "report": result_text,
    }


# 5. 중복 문제 확인
def normalize_question(question):
    return re.sub(r"\s+", "", question).casefold()


def existing_question_keys():
    keys = set()
    offset = 0
    page_size = 1000

    while True:
        response = (
            supabase.table("quizzes")
            .select("question")
            .range(offset, offset + page_size - 1)
            .execute()
        )

        rows = response.data or []

        for row in rows:
            keys.add(normalize_question(row["question"]))

        if len(rows) < page_size:
            break

        offset += page_size

    return keys


# 6. Supabase 저장
def save_quiz(quiz, topic_id, difficulty, quiz_type, source):
    payload = {
        "category_id": topic_id,
        "type": quiz_type,
        "difficulty": difficulty,
        "question": quiz.question,
        "correct_answer": quiz.correct_answer.strip().upper(),
        "explanation": quiz.explanation,
        "retry_hint": quiz.retry_hint,
        "source_title": source["title"],
        "source_url": source["url"],
        "verification_status": "pending",
    }

    result = (
        supabase.table("quizzes")
        .insert(payload)
        .execute()
    )

    if not result.data:
        raise RuntimeError("퀴즈 저장 실패")

    quiz_id = result.data[0]["id"]

    if quiz_type == "multiple_choice":
        options = [
            {
                "quiz_id": quiz_id,
                "option_key": option.option_key,
                "content": option.content,
            }
            for option in quiz.options
        ]

        try:
            (
                supabase.table("quiz_options")
                .insert(options)
                .execute()
            )
        except Exception:
            logger.exception(
                "선택지 저장 실패. 퀴즈 ID %s 확인 필요",
                quiz_id,
            )
            raise

    return quiz_id


# 7. 실패한 문제만 동일 조건으로 재생성
def generate_valid_quiz(
    client,
    topic,
    difficulty,
    quiz_type,
    existing,
    max_retries=10,
):
    for attempt in range(1, max_retries + 1):
        print(
            f"\n문제 생성 시도: {attempt}/{max_retries}"
        )

        try:
            quiz = generate_batch(
                client,
                topic,
                difficulty,
                quiz_type,
                1,
            )[0]

            key = normalize_question(quiz.question)

            # 중복 검사
            if key in existing:
                print(
                    "중복 문제 → 동일 조건으로 재생성"
                )
                continue

            # 출처 및 정답 검증
            verification = verify_quiz(
                client,
                quiz,
                topic,
                quiz_type,
            )

            if not verification["passed"]:
                print(
                    "검증 미통과 → 동일 조건으로 재생성"
                )
                print("문제:", quiz.question)
                print("검증 결과:", verification["report"])
                print("출처:", verification["sources"])
                continue

            return quiz, verification

        except Exception:
            logger.exception(
                "생성 또는 검증 오류 → 재시도"
            )

        time.sleep(2)

    raise RuntimeError(
        f"문제 생성 실패: "
        f"{topic}/{difficulty}/{quiz_type}"
    )


# 8. 전체 생성 실행
def run_generation(
    count=20,
    topic_filter=None,
    difficulty_filter=None,
    type_filter=None,
):
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise RuntimeError("GEMINI_API_KEY가 없습니다.")

    client = genai.Client(api_key=api_key)

    categories = (
        supabase.table("quiz_categories")
        .select("id, name")
        .execute()
    )

    category_map = {
        row["name"]: row["id"]
        for row in categories.data or []
    }

    # 필터에 해당하는 조건만 실행
    topics = [topic_filter] if topic_filter else TOPICS
    difficulties = (
        [difficulty_filter]
        if difficulty_filter else DIFFICULTIES
    )
    quiz_types = (
        [type_filter]
        if type_filter else QUIZ_TYPES
    )

    for topic in topics:
        if topic not in category_map:
            raise RuntimeError(
                f"카테고리 없음: {topic}"
            )

    existing = existing_question_keys()
    total_saved = 0

    for topic in topics:
        for difficulty in difficulties:
            for quiz_type in quiz_types:
                print(
                    f"\n{'=' * 50}"
                    f"\n생성 시작: "
                    f"{topic}/{difficulty}/{quiz_type}"
                    f"\n{'=' * 50}"
                )

                for number in range(1, count + 1):
                    print(
                        f"\n{number}/{count}번 문제"
                    )

                    quiz, verification = generate_valid_quiz(
                        client,
                        topic,
                        difficulty,
                        quiz_type,
                        existing,
                    )

                    source = verification["sources"][0]

                    quiz_id = save_quiz(
                        quiz,
                        category_map[topic],
                        difficulty,
                        quiz_type,
                        source,
                    )

                    existing.add(
                        normalize_question(quiz.question)
                    )

                    total_saved += 1

                    print(
                        f"저장 완료: ID={quiz_id}"
                    )

                    time.sleep(1)

    print(
        f"\n전체 저장 완료: {total_saved}문제"
    )


# 9. 실행 명령어 인자 설정
if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--count",
        type=int,
        default=20,
    )

    parser.add_argument(
        "--topic",
        type=str,
        choices=TOPICS,
        default=None,
    )

    parser.add_argument(
        "--difficulty",
        type=str,
        choices=DIFFICULTIES,
        default=None,
    )

    parser.add_argument(
        "--type",
        type=str,
        choices=QUIZ_TYPES,
        default=None,
    )

    args = parser.parse_args()

    if not 1 <= args.count <= 20:
        parser.error("--count는 1~20 사이여야 합니다.")

    run_generation(
        count=args.count,
        topic_filter=args.topic,
        difficulty_filter=args.difficulty,
        type_filter=args.type,
    )
