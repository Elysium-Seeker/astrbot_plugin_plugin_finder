import urllib.request
import re

req = urllib.request.Request(
    "https://plugins.astrbot.app/assets/index-BTYQR_DQ.js",
    headers={"User-Agent": "Mozilla/5.0"},
)
js = urllib.request.urlopen(req, timeout=5).read().decode("utf-8")
urls = re.findall(r"https?://[^\s\"\']+(?:\.json|/api/[^\s\"\']+)", js)
print("Found APIs:", set(urls))
