import os
from dotenv import load_dotenv

load_dotenv()

SNEHITH_API_URL = os.getenv("SNEHITH_API_URL")
SNEHITH_ADMIN_EMAIL = os.getenv("SNEHITH_ADMIN_EMAIL")
SNEHITH_ADMIN_PASSWORD = os.getenv("SNEHITH_ADMIN_PASSWORD")

if not SNEHITH_API_URL:
    raise RuntimeError("SNEHITH_API_URL is not configured")

if not SNEHITH_ADMIN_EMAIL:
    raise RuntimeError("SNEHITH_ADMIN_EMAIL is not configured")

if not SNEHITH_ADMIN_PASSWORD:
    raise RuntimeError("SNEHITH_ADMIN_PASSWORD is not configured")