import os
from getpass import getpass
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

client = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_SECRET_KEY"]
)

user_id = input("Supabase 사용자 UUID: ").strip()
new_password = getpass("새 비밀번호: ")

client.auth.admin.update_user_by_id(
    user_id,
    {"password": new_password}
)

print("비밀번호 변경 완료!")