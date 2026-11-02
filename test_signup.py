
from supabase import create_client
from app.core.config import SUPABASE_URL
import os

# 테스트에서는 공개용 키를 사용
SUPABASE_PUBLISHABLE_KEY = os.getenv("SUPABASE_PUBLISHABLE_KEY")

if not SUPABASE_PUBLISHABLE_KEY:
    raise RuntimeError("Publishable key가 설정되지 않았습니다.")

client = create_client(
    SUPABASE_URL,
    SUPABASE_PUBLISHABLE_KEY
)

response = client.auth.sign_up({
    "email": "choihanni27@gmail.com",
    "password": "TestPassword123!",
    "options": {
        "data": {
            "nickname": "테스트하마"
        }
    }
})

print("회원가입 요청 완료")
print("사용자 ID:", response.user.id if response.user else None)
