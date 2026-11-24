
import os
from dotenv import load_dotenv
from supabase import create_client
from getpass import getpass

load_dotenv()

client = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_PUBLISHABLE_KEY")
)

email = input("이메일: ")
password = getpass("비밀번호: ")

response = client.auth.sign_in_with_password({
    "email": email,
    "password": password
})

print("로그인 성공!")
print("사용자 ID:", response.user.id)
print("Access Token:", response.session.access_token)
