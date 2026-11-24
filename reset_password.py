import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

client = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_PUBLISHABLE_KEY"]
)

email = input("이메일: ")

client.auth.reset_password_email(email)

print("비밀번호 재설정 이메일 요청 완료!")