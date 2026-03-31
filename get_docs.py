import json
import urllib.request
import re

req = urllib.request.Request('https://docs.astrbot.app/what-is-astrbot.html', headers={'User-Agent': 'Mozilla/5.0'})
html = urllib.request.urlopen(req).read().decode('utf-8')
print(re.findall(r'href=[\'\"](/[^\'\"]+\.html)[\'\"]', html))