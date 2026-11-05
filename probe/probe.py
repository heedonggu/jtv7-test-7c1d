"""iOS 시뮬레이터 사파리에서 'vcf 여러 명 저장' 화면을 실제로 눌러 보고 화면·UI 트리를 남긴다.
WebDriverAgent(8100) HTTP API만 쓴다. 가짜 명단만 다룬다. (v2: predicate string, 대기 후 탭)"""
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


def find(pred):
    return eid_of(call("POST", S("/element"), {"using": "predicate string", "value": pred}, timeout=60))


def tap(pred):
    e = find(pred)
    if not e:
        return False
    r = call("POST", S(f"/element/{e}/click"))
    return "_http" not in r and "_err" not in r


def wait_tap(name, preds, timeout=45):
    t0 = time.time()
    while time.time() - t0 < timeout:
        for p in preds:
            if tap(p):
                say(f"[{name}] tapped: {p} (after {time.time() - t0:.0f}s)")
                time.sleep(2.5)
                return True
        time.sleep(1.5)
    say(f"[{name}] NOT FOUND after {timeout}s: {preds}")
    return False


def wait_for(name, preds, timeout=45):
    t0 = time.time()
    while time.time() - t0 < timeout:
        for p in preds:
            if find(p):
                say(f"[{name}] seen: {p} (after {time.time() - t0:.0f}s)")
                return True
        time.sleep(1.5)
    say(f"[{name}] NOT SEEN after {timeout}s: {preds}")
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
        item = f"{t}:{label[:48]}"
        if t in ("Button", "Link", "Cell", "MenuItem", "Alert", "Sheet", "StaticText", "Other") and item not in labs:
            labs.append(item)
    say(f"== {name}: " + " | ".join(labs[:90]))


def openurl(u):
    subprocess.run(["xcrun", "simctl", "openurl", "booted", u], check=False)
    time.sleep(4)


def launch(bid):
    call("POST", S("/wda/apps/launch"), {"bundleId": bid})
    time.sleep(3)


def terminate(bid):
    call("POST", S("/wda/apps/terminate"), {"bundleId": bid})
    time.sleep(1)


def flow_inline():  # 링크를 그냥 열었을 때: 미리보기 -> 공유
    terminate("com.apple.mobilesafari")
    openurl(BASE + "m/2.vcf")
    wait_for("inline-preview", ["label == 'Create New Contact'"], 60)
    snap("10-inline-vcf")
    wait_tap("inline-share", ["label == 'Share'", "name == 'Share'"], 20)
    snap("11-inline-share-sheet")
    # 공유 시트에서 연락처 관련 항목이 있으면 눌러 본다
    if wait_tap("share-contacts", ["label == 'Contacts'", "label CONTAINS[c] 'add all'", "label CONTAINS[c] 'contacts'"], 10):
        snap("12-inline-after-contacts")
        wait_tap("add-all", ["label CONTAINS[c] 'add all'"], 10)
        snap("13-inline-after-add-all")


def flow_download():  # 우리 페이지: 저장 -> 다운로드 -> 목록 -> 파일 -> 공유
    terminate("com.apple.mobilesafari")
    openurl(BASE + "?me=2")
    wait_for("page", ["label CONTAINS '명 저장'"], 60)
    snap("20-page")
    wait_tap("save", ["label CONTAINS '명 저장'"], 20)
    snap("21-after-save-tap")
    wait_tap("download-prompt", ["label == 'Download'", "label CONTAINS[c] 'download'"], 25)
    snap("22-after-download")
    wait_tap("downloads-button", ["label == 'Downloads'", "label CONTAINS[c] 'downloads'", "name CONTAINS[c] 'download'"], 25)
    snap("23-downloads-list")
    wait_tap("file", ["label CONTAINS 'JTV7'", "label CONTAINS 'vcf'"], 20)
    snap("24-preview")
    wait_tap("share", ["label == 'Share'", "label CONTAINS[c] 'share'"], 15)
    snap("25-share-sheet")
    if wait_tap("contacts-action", ["label == 'Contacts'", "label CONTAINS[c] 'contacts'"], 10):
        snap("26-after-contacts-action")
        wait_tap("add-all", ["label CONTAINS[c] 'add all'"], 10)
        snap("27-after-add-all")


def flow_files():  # 파일 앱에서 받은 파일 열기
    launch("com.apple.DocumentsApp")
    snap("30-files")
    wait_tap("browse", ["label == 'Browse'"], 20)
    snap("31-browse")
    wait_tap("on-my-iphone", ["label CONTAINS 'On My iPhone'"], 15)
    snap("32-on-my-iphone")
    wait_tap("downloads-folder", ["label == 'Downloads'"], 15)
    snap("33-downloads-folder")
    wait_tap("file", ["label CONTAINS 'JTV7'", "label CONTAINS 'vcf'"], 15)
    snap("34-file-preview")
    wait_tap("share", ["label == 'Share'", "label CONTAINS[c] 'share'"], 15)
    snap("35-share-sheet")
    if wait_tap("contacts", ["label == 'Contacts'", "label CONTAINS[c] 'contacts'"], 10):
        snap("36-after-contacts")
        wait_tap("add-all", ["label CONTAINS[c] 'add all'"], 10)
        snap("37-after-add-all")


def flow_webshare():  # 웹 공유 시트(파일 첨부)에 무엇이 뜨는지
    terminate("com.apple.mobilesafari")
    openurl("http://localhost:8000/webshare.html")
    wait_for("webshare-page", ["label CONTAINS 'SHARE-VCF'"], 60)
    snap("40-webshare-page")
    wait_tap("share-btn", ["label CONTAINS 'SHARE-VCF'"], 20)
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
