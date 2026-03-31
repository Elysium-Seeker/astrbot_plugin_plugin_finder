import urllib.request
from bs4 import BeautifulSoup
import re

urls = [
    "https://docs.astrbot.app/dev/star/plugin-new.html",
    "https://docs.astrbot.app/dev/openapi.html",
    "https://docs.astrbot.app/use/plugin.html",
]

for url in urls:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        html = urllib.request.urlopen(req).read().decode("utf-8")
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text()
        print(f"\n--- {url} ---")

        matches = re.finditer(
            r".{0,50}(hot-reload|reload|restart|directory|data/plugins|API|api/v1).{0,50}",
            text,
            re.IGNORECASE,
        )
        for m in matches:
            print(m.group(0).replace("\n", " "))
    except Exception as e:
        print(f"Error {url}: {e}")
