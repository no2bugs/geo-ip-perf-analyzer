#!/usr/bin/env python3
import re

with open("web/static/config.js") as f:
    js = f.read()
with open("web/templates/config.html") as f:
    html = f.read()

ids_used = set(re.findall(r"getElementById\(['\"]([^'\"]+)['\"]\)", js))
ids_in_html = set(re.findall(r'id="([^"]+)"', html))
missing = ids_used - ids_in_html
if missing:
    print("MISSING IDs:", sorted(missing))
    for m in sorted(missing):
        lines = [i+1 for i, line in enumerate(js.split("\n")) if "getElementById" in line and m in line]
        print(f"  {m} used at lines: {lines}")
else:
    print("All IDs found in HTML")
