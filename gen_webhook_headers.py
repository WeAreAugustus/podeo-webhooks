"""Generate token and date for Podeo webhook Postman headers. Run: python gen_webhook_headers.py"""
import hashlib
from datetime import datetime

CLIENT_ID = "181979"
CLIENT_SECRET = "dOKDNFxKcSKLEX1apxmV8jAVmxNyW0VTvUa4okZb"
now = datetime.utcnow()
date = f"{now.day}-{now.month}-{now.year}"
s = f"{CLIENT_SECRET}_{CLIENT_ID}__{date}"
token = hashlib.sha256(s.encode("utf-8")).hexdigest()
print("date:", date)
print("token:", token)
