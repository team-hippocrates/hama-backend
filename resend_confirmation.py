
import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

client = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_PUBLISHABLE_KEY")
)

response = client.auth.resend({
    "type": "signup",
    "email": "choihanni27@gmail.com"
})

print("인증 메일 재발송 요청 완료")
