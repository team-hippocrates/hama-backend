import logging
from fastapi import FastAPI, HTTPException
from app.db.supabase import supabase
from fastapi import Depends
from app.core.security import get_current_user

logger = logging.getLogger(__name__)

app = FastAPI(title="똑똑하마 API")


@app.get("/")
def root():
    return {"message": "똑똑하마 API 서버 실행 성공!"}


@app.get("/api/v1/db-test")
def db_test():
    try:
        response = (
            supabase.table("quiz_categories")
            .select("id, name")
            .limit(1)
            .execute()
        )

        return {
            "status": "success",
            "message": "Supabase 연결 성공!",
            "data": response.data
        }

    except Exception:
        logger.exception("Supabase DB 조회 중 오류 발생")

        raise HTTPException(
            status_code=503,
            detail="Supabase 연결 실패"
        )

@app.get("/api/v1/users/me")    
def get_my_profile(user=Depends(get_current_user)):
    response = (
        supabase.table("profiles")
        .select("id, nickname, created_at")
        .eq("id", str(user.id))
        .single()
        .execute()
    )

    return {
        "id": str(user.id),
        "email": user.email,
        "profile": response.data
    }
