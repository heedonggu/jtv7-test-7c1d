"""iOS 시뮬레이터 사파리에서 'vcf 여러 명 저장' 화면을 실제로 눌러 보고 화면·UI 트리를 남긴다.
WebDriverAgent(8100) HTTP API만 쓴다. 가짜 명단만 다룬다.
(v6: 연락처 DB를 직접 세어 중복을 확인하고, '모든 연락처 추가' 머리글 선택지도 시험한다)"""
import base64
import json
import os
import pathlib
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request

OUT = pathlib.Path(os.environ.get("OUT", "shots"))
OUT.mkdir(parents=True, exist_ok=True)
WDA = "http://127.0.0.1:8100"
BASE = f"http://localhost:8000/{os.environ['SLUG']}/"
PICK = int(os.environ.get("PICK", "0"))  # 공유 시트의 'Contacts' 두 개 중 몇 번째를 누를지
ACTION = os.environ.get("ACTION", "save")  # save: 오른쪽 위 Save / header: 'Add All N Contacts' 머리글을 눌러 선택지를 본다
OPT = int(os.environ.get("OPT", "0"))  # header일 때 나온 선택지 중 몇 번째를 누를지
LOG = open(OUT / "log.txt", "w", encoding="utf-8")
sid = None
BSL = chr(92)  # 역슬래시 (정규식 이스케이프 오타 방지)
LABEL_RE = re.compile(r"<XCUIElementType(" + BSL + r"w+)[^>]*?" + BSL + r'blabel="([^"]*)"')


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
    for t, label in LABEL_RE.findall(xml):
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


def db_counts(tag):  # 시뮬레이터 연락처 DB를 직접 센다(이름별 개수)
    udid = os.environ.get("UDID", "")
    root = pathlib.Path.home() / "Library/Developer/CoreSimulator/Devices" / udid / "data"
    found = list(root.glob("Library/AddressBook/AddressBook.sqlitedb")) or list(root.glob("**/AddressBook.sqlitedb"))
    if not found:
        say(f"DB[{tag}]: AddressBook.sqlitedb not found under {root}")
        return None
    tmp = pathlib.Path("/tmp/abcopy")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir()
    for f in found[0].parent.glob("AddressBook.sqlitedb*"):
        shutil.copy(f, tmp / f.name)
    q = "select First, count(*) from ABPerson group by First order by First;"
    r = subprocess.run(["sqlite3", str(tmp / "AddressBook.sqlitedb"), q], capture_output=True, text=True)
    say(f"DB[{tag}]: " + r.stdout.strip().replace(chr(10), " | ") + " " + r.stderr.strip()[:200])
    return r.stdout


def contacts_app(tag):
    launch("com.apple.MobileAddressBook")
    snap(tag)


def open_page():
    terminate("com.apple.mobilesafari")
    openurl(BASE + "?me=2")
    wait_for("page", ["label CONTAINS '명 저장'"], 60)
    tips()


def count_label():
    es = find_all("label ENDSWITH '명 선택'")
    if not es:
        return None
    return call("GET", S(f"/element/{es[0]}/attribute/label")).get("value")


def select_only(names):  # 모두 해제 후 원하는 사람만 체크(탭이 빗나가면 다시 누른다)
    tap("label == '모두 해제'")
    time.sleep(1)
    n = 0
    for name in names:
        for _ in range(3):
            tap(f"type == 'XCUIElementTypeStaticText' AND label == '{name}'")
            time.sleep(1)
            if count_label() == f"{n + 1}명 선택":
                n += 1
                break
    say("[select_only] count label:", count_label())


def button_labels(xml):
    return [label for t, label in LABEL_RE.findall(xml) if t in ("Button", "MenuItem", "Cell") and label]


def share_to_contacts(tag, action):
    if not wait_for("preview", ["label == 'Create New Contact'", "label BEGINSWITH 'Update Contact'"], 60):
        snap(tag + "-no-preview")
        return False
    tips()
    snap(tag + "-preview")
    if not wait_tap("share", ["label == 'Share'"], 15):
        snap(tag + "-no-share-button")
        return False
    snap(tag + "-share-sheet")
    if not wait_tap("contacts", ["type == 'XCUIElementTypeCell' AND label == 'Contacts'"], 10, n=PICK):
        return False
    # 가져오기 화면(오른쪽 위 Save)이 뜰 때까지 기다린다. 제목(Add All N Contacts)이 안 읽혀도 Save는 찾힌다.
    if not wait_for("import-ui", ["label == 'Save'"], 30):
        snap(tag + "-no-import-ui")
        return False
    xml = snap(tag + "-import-sheet")
    m = re.search(r"Add All (" + BSL + r"d+) Contacts", xml)
    say("IMPORT-SHEET title:", m.group(0) if m else None)
    if action == "save":
        wait_tap("save", ["label == 'Save'"], 10)
        time.sleep(3)
        return True
    # header: 'Add All N Contacts' 머리글을 눌러 나오는 선택지를 본다
    before = set(button_labels(xml))
    if not wait_tap("header", ["label BEGINSWITH 'Add All'"], 10):
        say("[header] not tappable")
        return False
    xml2 = snap(tag + "-header-options")
    new = [x for x in button_labels(xml2) if x not in before and x not in ("Cancel",)]
    say("HEADER-OPTIONS (new buttons):", new)
    if len(new) > OPT:
        pick = new[OPT]
        say("[header] choosing option:", pick)
        wait_tap("header-option", [f"label == '{pick}'"], 10)
        time.sleep(3)
        snap(tag + "-after-option")
        return True
    say("[header] no such option index", OPT)
    return False


def flow_partial():  # 일부만 고르고 저장 -> 고른 사람만 들어갔는지
    db_counts("00-before")
    open_page()
    select_only(["김하나", "정다섯", "한여섯"])
    snap("10-page-selected")
    wait_tap("save3", ["label CONTAINS '3명 저장'"], 10)
    share_to_contacts("11-partial", "save")
    db_counts("12-after-partial")
    contacts_app("12-contacts-app")


def flow_full_dup():  # 이미 3명 있는 상태에서 전원 5명 -> 중복이 생기는지(ACTION/OPT 별로)
    open_page()
    snap("20-page-full")
    wait_tap("save5", ["label CONTAINS '5명 저장'"], 10)
    share_to_contacts("21-full", ACTION)
    db_counts("22-after-full")
    contacts_app("22-contacts-app")


if __name__ == "__main__":
    subprocess.run("sw_vers; xcrun simctl list devices booted; xcrun simctl list runtimes", shell=True, check=False)
    say("ACTION", ACTION, "OPT", OPT, "PICK", PICK)
    session()
    for f in (flow_partial, flow_full_dup):
        try:
            f()
        except Exception as e:  # noqa: BLE001
            say("FLOW ERROR", f.__name__, repr(e))
    say("done")
