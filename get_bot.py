import json
import urllib.request

url = "https://api.github.com/repos/Soulter/AstrBot/git/trees/main?recursive=1"
try:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    text = urllib.request.urlopen(req).read().decode("utf-8")
    data = json.loads(text)
    for f in data.get("tree", []):
        if "plugin" in f["path"] or "reload" in f["path"] or "manager" in f["path"]:
            print(f["path"])
except Exception as e:
    print(e)
