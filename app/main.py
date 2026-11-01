from fastapi import FastAPI, HTTPException
from app.db.supabase import supabase
import uvicorn

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
        raise HTTPException(
            status_code=503,
            detail="Supabase 연결 실패"
        )

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )