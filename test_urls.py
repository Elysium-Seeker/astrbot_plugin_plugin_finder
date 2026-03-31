import urllib.request
import re

try:
    req = urllib.request.Request(
        "https://plugins.astrbot.app/assets/index-BTYQR_DQ.js",
        headers={"User-Agent": "Mozilla/5.0"},
    )
    html = urllib.request.urlopen(req).read().decode("utf-8")
    urls = re.findall(r"https://[a-zA-Z0-9\-\.\/]+", html)
    print("Found URLs:", urls)
except Exception as e:
    print("Error:", e)
