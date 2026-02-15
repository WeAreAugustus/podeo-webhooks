"""Generate token and date for Podeo webhook Postman headers. Run: python gen_webhook_headers.py"""
import hashlib
import os
from datetime import datetime

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

CLIENT_ID = (os.getenv("PODEO_CLIENT_ID") or "181979").strip().strip('"')
CLIENT_SECRET = (os.getenv("PODEO_CLIENT_SECRET") or "dOKDNFxKcSKLEX1apxmV8jAVmxNyW0VTvUa4okZb").strip().strip('"')

now = datetime.utcnow()
date = f"{now.day}-{now.month}-{now.year}"
s = f"{CLIENT_SECRET}_{CLIENT_ID}__{date}"
token = hashlib.sha256(s.encode("utf-8")).hexdigest()
print("date:", date)
print("token:", token)
