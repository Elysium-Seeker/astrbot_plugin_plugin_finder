import urllib.request
import re

urls = [
    "https://docs.astrbot.app/dev/star/plugin-new.html",
    "https://docs.astrbot.app/dev/openapi.html",
    "https://docs.astrbot.app/use/plugin.html",
]

out = open("result.txt", "w", encoding="utf-8")
for url in urls:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        html = urllib.request.urlopen(req).read().decode("utf-8")
        # strip html tags
        text = re.sub(r"<[^>]+>", " ", html)
        out.write(f"\n--- {url} ---\n")

        for m in re.finditer(
            r".{0,60}(hot-reload|reload|restart|directory|data/plugins|API|api/v1).{0,60}",
            text,
            re.IGNORECASE,
        ):
            out.write(m.group(0).replace("\n", " ") + "\n")
    except Exception as e:
        out.write(f"Error {url}: {e}\n")
out.close()
