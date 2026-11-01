import os
from dotenv import load_dotenv

load_dotenv()

# 환경 변수 이름으로 값 가져오기
SUPABASE_URL = os.getenv("SUPABASE_URL") 
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY")

if not SUPABASE_URL or not SUPABASE_SECRET_KEY:
    raise RuntimeError("Supabase 환경 변수가 설정되지 않았습니다.")