"""Print a PBKDF2 password hash for WEB_ADMIN_PASSWORD_HASH in .env."""
from __future__ import annotations

import hashlib
import secrets
from getpass import getpass

ITERATIONS = 390_000


def main() -> None:
    password = getpass("Yangi veb-admin parolini kiriting (kamida 12 belgi): ")
    confirm = getpass("Parolni qayta kiriting: ")
    if password != confirm:
        raise SystemExit("Parollar mos kelmadi.")
    if len(password) < 12:
        raise SystemExit("Xavfsizlik uchun parol kamida 12 belgidan iborat bo‘lsin.")
    salt = secrets.token_urlsafe(18)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), ITERATIONS).hex()
    print("\nWEB_ADMIN_PASSWORD_HASH qiymati (butun satrni .env ga nusxalang):")
    print(f"pbkdf2_sha256${ITERATIONS}${salt}${digest}")
    print("\nADMIN_SESSION_SECRET uchun alohida tasodifiy kalit yarating: python -c \"import secrets; print(secrets.token_urlsafe(48))\"")


if __name__ == "__main__":
    main()
