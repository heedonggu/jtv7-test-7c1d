"""가장 새 iOS 런타임의 iPhone(가능하면 Pro Max)을 골라 UDID를 출력한다."""
import json
import subprocess
import sys

devs = json.loads(subprocess.check_output(["xcrun", "simctl", "list", "devices", "available", "-j"]))["devices"]
best = None
for rt, items in devs.items():
    if "iOS" not in rt:
        continue
    try:
        ver = tuple(int(x) for x in rt.split("iOS-")[1].split("-"))
    except Exception:
        continue
    for d in items:
        if "iPhone" not in d["name"]:
            continue
        score = (ver, "Pro Max" in d["name"], d["name"])
        if best is None or score > best[0]:
            best = (score, d["udid"], d["name"], rt)
print(best[1])
print("device:", best[2], best[3], file=sys.stderr)
