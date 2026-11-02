
import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

client = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_PUBLISHABLE_KEY")
)

response = client.auth.sign_in_with_password({
    "email": "choihanni27@gmail.com",
    "password": "TestPassword123!"
})

print("로그인 성공!")
print("사용자 ID:", response.user.id)
print("Access Token:", response.session.access_token)
