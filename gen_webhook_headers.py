"""Generate token and date for Podeo webhook Postman headers. Run: python gen_webhook_headers.py"""
import hashlib
from datetime import datetime

CLIENT_ID = "4564"
CLIENT_SECRET = "I3cLUutIv22EijgawfKiGJVn40x8GYacdQhvfgFZ"
date = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")
s = f"{CLIENT_SECRET}_{CLIENT_ID}__{date}"
token = hashlib.sha256(s.encode()).hexdigest()
print("date:", date)
print("token:", token)
