"""iOS 시뮬레이터 사파리에서 'vcf 여러 명 저장' 화면을 실제로 눌러 보고 화면·UI 트리를 남긴다.
WebDriverAgent(8100) HTTP API만 쓴다. 가짜 명단만 다룬다."""
import base64
import json
import os
import pathlib
import re
import subprocess
import time
import urllib.error
import urllib.request

OUT = pathlib.Path(os.environ.get("OUT", "shots"))
OUT.mkdir(parents=True, exist_ok=True)
WDA = "http://127.0.0.1:8100"
BASE = f"http://localhost:8000/{os.environ['SLUG']}/"
LOG = open(OUT / "log.txt", "w", encoding="utf-8")
sid = None


def say(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    LOG.write(s + "\n")
    LOG.flush()


def call(method, path, body=None, timeout=120):
    data = None if body is None else json.dumps(body).encode()
    rq = urllib.request.Request(WDA + path, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(rq, timeout=timeout) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            b = json.loads(e.read().decode() or "{}")
        except Exception:
            b = {}
        return {"_http": e.code, **b}
    except Exception as e:  # noqa: BLE001
        return {"_err": str(e)}


def session():
    global sid
    r = call("POST", "/session", {"capabilities": {"alwaysMatch": {}}, "desiredCapabilities": {}})
    sid = r.get("sessionId") or (r.get("value") or {}).get("sessionId")
    say("session", sid, str(r)[:160])


def S(p):
    return f"/session/{sid}{p}"


def eid_of(r):
    v = r.get("value")
    if isinstance(v, dict):
        return v.get("ELEMENT") or v.get("element-6066-11e4-a52e-4f735466cecf")
    return None


def tap(pred):
    e = eid_of(call("POST", S("/element"), {"using": "-ios predicate string", "value": pred}))
    if not e:
        return False
    r = call("POST", S(f"/element/{e}/click"))
    return "_http" not in r and "_err" not in r


def tap_any(name, *preds):
    for p in preds:
        if tap(p):
            say(f"[{name}] tapped: {p}")
            time.sleep(2.5)
            return True
    say(f"[{name}] NOT FOUND: {preds}")
    return False


def snap(name):
    time.sleep(1.5)
    r = call("GET", S("/screenshot"))
    b = r.get("value")
    if isinstance(b, str):
        (OUT / f"{name}.png").write_bytes(base64.b64decode(b))
    else:
        subprocess.run(["xcrun", "simctl", "io", "booted", "screenshot", str(OUT / f"{name}.png")], check=False)
    s = call("GET", S("/source"))
    xml = s.get("value") if isinstance(s.get("value"), str) else json.dumps(s)[:2000]
    (OUT / f"{name}.xml").write_text(xml, encoding="utf-8")
    labs = []
    for m in re.finditer(r'<XCUIElementType(\w+)[^>]*?\blabel="([^"]+)"', xml):
        t, label = m.group(1), m.group(2)
        item = f"{t}:{label[:60]}"
        if t in ("Button", "Link", "Cell", "MenuItem", "Alert", "Sheet", "StaticText", "Other") and item not in labs:
            labs.append(item)
    say(f"== {name}: " + " | ".join(labs[:80]))


def openurl(u):
    subprocess.run(["xcrun", "simctl", "openurl", "booted", u], check=False)
    time.sleep(6)


def launch(bid):
    call("POST", S("/wda/apps/launch"), {"bundleId": bid})
    time.sleep(3)


def terminate(bid):
    call("POST", S("/wda/apps/terminate"), {"bundleId": bid})
    time.sleep(1)


def flow_inline():  # 링크를 그냥 열었을 때(대표 폰: 한 명짜리 미리보기)
    terminate("com.apple.mobilesafari")
    openurl(BASE + "m/2.vcf")
    snap("10-inline-vcf")
    tap_any("inline-share", "label == 'Share'", "label CONTAINS[c] 'share'")
    snap("11-inline-after-share-try")
    tap_any("inline-close", "label == 'Done'", "label == 'Cancel'", "label == 'Close'")


def flow_download():  # 우리 페이지: 저장 -> 다운로드 -> 목록 -> 파일 -> 공유
    terminate("com.apple.mobilesafari")
    openurl(BASE + "?me=2")
    snap("20-page")
    tap_any("save", "label CONTAINS '명 저장'")
    snap("21-after-save-tap")
    tap_any("download-prompt", "label == 'Download'", "label CONTAINS[c] 'download'")
    snap("22-after-download")
    tap_any("downloads-button", "label == 'Downloads'", "name == 'Downloads'", "label CONTAINS[c] 'downloads'")
    snap("23-downloads-list")
    tap_any("file", "label CONTAINS 'JTV7'", "label CONTAINS 'vcf'")
    snap("24-preview")
    tap_any("share", "label == 'Share'", "label CONTAINS[c] 'share'")
    snap("25-share-sheet")
    tap_any("contacts-action", "label == 'Contacts'", "label CONTAINS[c] 'contact'")
    snap("26-after-contacts-action")
    tap_any("add-all", "label CONTAINS[c] 'add all'")
    snap("27-after-add-all")


def flow_files():  # 파일 앱에서 받은 파일 열기
    launch("com.apple.DocumentsApp")
    snap("30-files")
    tap_any("browse", "label == 'Browse'")
    snap("31-browse")
    tap_any("on-my-iphone", "label CONTAINS 'On My iPhone'")
    snap("32-on-my-iphone")
    tap_any("downloads-folder", "label == 'Downloads'")
    snap("33-downloads-folder")
    tap_any("file", "label CONTAINS 'JTV7'", "label CONTAINS 'vcf'")
    snap("34-file-preview")
    tap_any("share", "label == 'Share'", "label CONTAINS[c] 'share'")
    snap("35-share-sheet")
    tap_any("contacts", "label == 'Contacts'", "label CONTAINS[c] 'contact'")
    snap("36-after-contacts")
    tap_any("add-all", "label CONTAINS[c] 'add all'")
    snap("37-after-add-all")


def flow_webshare():  # 웹 공유 시트(파일 첨부)에 무엇이 뜨는지
    terminate("com.apple.mobilesafari")
    openurl("http://localhost:8000/webshare.html")
    snap("40-webshare-page")
    tap_any("share-btn", "label CONTAINS 'SHARE-VCF'")
    snap("41-webshare-sheet")


if __name__ == "__main__":
    subprocess.run("sw_vers; xcrun simctl list devices booted; xcrun simctl list runtimes", shell=True, check=False)
    session()
    for f in (flow_inline, flow_download, flow_files, flow_webshare):
        try:
            f()
        except Exception as e:  # noqa: BLE001
            say("FLOW ERROR", f.__name__, repr(e))
    say("done")
