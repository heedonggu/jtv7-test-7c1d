"""iOS 시뮬레이터 사파리에서 'vcf 여러 명 저장' 화면을 실제로 눌러 보고 화면·UI 트리를 남긴다.
WebDriverAgent(8100) HTTP API만 쓴다. 가짜 명단만 다룬다. (v3: 공유->연락처 가져오기 후 연락처 앱 인원 세기)"""
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
PICK = int(os.environ.get("PICK", "0"))  # 공유 시트의 'Contacts' 두 개 중 몇 번째를 누를지
LOG = open(OUT / "log.txt", "w", encoding="utf-8")
sid = None
HANGUL = re.compile(r'label="([가-힣]{2,4})"')


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


def ids(r):
    v = r.get("value")
    if isinstance(v, dict):
        v = [v]
    out = []
    for x in v or []:
        if isinstance(x, dict):
            e = x.get("ELEMENT") or x.get("element-6066-11e4-a52e-4f735466cecf")
            if e:
                out.append(e)
    return out


def find_all(pred):
    return ids(call("POST", S("/elements"), {"using": "predicate string", "value": pred}, timeout=60))


def click(e):
    r = call("POST", S(f"/element/{e}/click"))
    return "_http" not in r and "_err" not in r


def tap(pred, n=0):
    es = find_all(pred)
    return len(es) > n and click(es[n])


def wait_tap(name, preds, timeout=45, n=0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        for p in preds:
            if tap(p, n):
                say(f"[{name}] tapped: {p} #{n} (after {time.time() - t0:.0f}s)")
                time.sleep(2.5)
                return True
        time.sleep(1.5)
    say(f"[{name}] NOT FOUND after {timeout}s: {preds} #{n}")
    return False


def wait_for(name, preds, timeout=45):
    t0 = time.time()
    while time.time() - t0 < timeout:
        for p in preds:
            if find_all(p):
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
    return xml


def openurl(u):
    subprocess.run(["xcrun", "simctl", "openurl", "booted", u], check=False)
    time.sleep(4)


def launch(bid):
    call("POST", S("/wda/apps/launch"), {"bundleId": bid})
    time.sleep(3)


def terminate(bid):
    call("POST", S("/wda/apps/terminate"), {"bundleId": bid})
    time.sleep(1)


def tips():  # 사파리 첫 실행 안내 말풍선 닫기
    for p in ("label == 'dismiss popup'", "label == 'Not Now'", "label == 'Continue'"):
        if tap(p):
            say("[tips] dismissed via", p)
            time.sleep(1)


def contacts_count(tag):
    launch("com.apple.MobileAddressBook")
    xml = snap(tag)
    names = sorted(set(HANGUL.findall(xml)))
    say(f"CONTACTS[{tag}]: {len(names)} -> {names}")
    return names


def flow_inline_import():  # 링크 미리보기 -> 공유 -> 연락처 가져오기 -> 연락처 앱에서 인원 세기(두 번 반복해 중복도 본다)
    contacts_count("05-contacts-before")
    for rnd in (1, 2):
        terminate("com.apple.mobilesafari")
        openurl(BASE + "m/2.vcf")
        wait_for("inline-preview", ["label == 'Create New Contact'"], 60)
        tips()
        snap(f"1{rnd}0-inline-vcf")
        if not wait_tap("inline-share", ["label == 'Share'", "name == 'Share'"], 15):
            snap(f"1{rnd}1-no-share-button")
            break
        snap(f"1{rnd}1-share-sheet")
        if wait_tap("share-contacts", ["type == 'XCUIElementTypeCell' AND label == 'Contacts'", "label == 'Contacts'"], 10, n=PICK):
            for i in range(3):
                snap(f"1{rnd}2-after-contacts-{i}")
                for p in ("label CONTAINS[c] 'add all'", "label CONTAINS[c] 'create new contacts'", "label == 'Done'", "label == 'Save'", "label == 'Add'"):
                    if tap(p):
                        say("[after-contacts] tapped", p)
                        time.sleep(2)
                        break
                else:
                    break
        contacts_count(f"1{rnd}3-contacts-after-import-{rnd}")


def flow_download():  # 우리 페이지: 저장 -> 다운로드 -> 목록 -> 파일 -> 공유
    terminate("com.apple.mobilesafari")
    openurl(BASE + "?me=2")
    wait_for("page", ["label CONTAINS '명 저장'"], 60)
    tips()
    snap("20-page")
    wait_tap("save", ["label CONTAINS '명 저장'"], 20)
    snap("21-after-save-tap")
    wait_tap("download-prompt", ["type == 'XCUIElementTypeButton' AND label == 'Download'", "type == 'XCUIElementTypeButton' AND label CONTAINS[c] 'download'"], 15)
    snap("22-after-download")
    wait_tap("downloads-button", ["type == 'XCUIElementTypeButton' AND label CONTAINS[c] 'download'"], 15)
    snap("23-downloads-list")
    if wait_tap("file", ["type != 'XCUIElementTypeOther' AND type != 'XCUIElementTypeStaticText' AND label CONTAINS 'JTV7'"], 10):
        snap("24-preview")
        if wait_tap("share", ["label == 'Share'"], 10):
            snap("25-share-sheet")


def flow_files():  # 파일 앱에서 받은 파일 열기
    launch("com.apple.DocumentsApp")
    snap("30-files")
    wait_tap("browse", ["label == 'Browse'"], 20)
    snap("31-browse")
    wait_tap("on-my-iphone", ["label CONTAINS 'On My iPhone'"], 15)
    snap("32-on-my-iphone")
    wait_tap("downloads-folder", ["label == 'Downloads'"], 8)
    snap("33-downloads-folder")
    if wait_tap("file", ["type != 'XCUIElementTypeOther' AND type != 'XCUIElementTypeStaticText' AND label CONTAINS 'JTV7'"], 8):
        snap("34-file-preview")
        if wait_tap("share", ["label == 'Share'"], 10):
            snap("35-share-sheet")


def flow_webshare():  # 웹 공유 시트(파일 첨부)에 무엇이 뜨는지
    terminate("com.apple.mobilesafari")
    openurl("http://localhost:8000/webshare.html")
    wait_for("webshare-page", ["label CONTAINS 'SHARE-VCF'"], 60)
    tips()
    snap("40-webshare-page")
    wait_tap("share-btn", ["label CONTAINS 'SHARE-VCF'"], 20)
    snap("41-webshare-sheet")


if __name__ == "__main__":
    subprocess.run("sw_vers; xcrun simctl list devices booted; xcrun simctl list runtimes", shell=True, check=False)
    session()
    for f in (flow_inline_import, flow_download, flow_files, flow_webshare):
        try:
            f()
        except Exception as e:  # noqa: BLE001
            say("FLOW ERROR", f.__name__, repr(e))
    say("done")
