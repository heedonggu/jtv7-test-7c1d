"""iOS 시뮬레이터 사파리에서 'vcf 여러 명 저장' 화면을 실제로 눌러 보고 연락처 DB를 직접 센다.
WebDriverAgent(8100) HTTP API만 쓴다. 가짜 명단만 다룬다.
v8: 화면은 /source(XML)만 읽고 누르기는 좌표 터치로 한다(처음 켠 연락처 앱에서 /elements가 120초간 못 찾던 문제 회피).
    머리글 'Add All N Contacts' -> 'Add All N Contacts' -> 뜨는 확인창('Create New Contacts' 등)까지 끝까지 눌러 DB를 센다."""
import base64
import json
import os
import pathlib
import shutil
import subprocess
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

OUT = pathlib.Path(os.environ.get("OUT", "shots"))
OUT.mkdir(parents=True, exist_ok=True)
WDA = "http://127.0.0.1:8100"
SITE = "http://localhost:8000/"
BASE = SITE + f"{os.environ['SLUG']}/"
PICK = int(os.environ.get("PICK", "0"))  # 공유 시트의 'Contacts' 두 개 중 몇 번째를 누를지
LOG = open(OUT / "log.txt", "w", encoding="utf-8")
SAMPLE = ("Anna", "Daniel", "David", "Hank", "John", "Kate")
sid = None
W, H = 440.0, 956.0  # 화면(pt). session()에서 window/size로 덮어쓴다
PREFER = ("Create New Contact", "Update", "Merge", "Add", "OK", "Continue")  # 확인창에서 눌러도 되는 버튼(앞쪽 우선). 'Create New Contact'는 단수·복수 모두 잡는다


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


def S(p):
    return f"/session/{sid}{p}"


def session():
    global sid, W, H
    r = call("POST", "/session", {"capabilities": {"alwaysMatch": {}}, "desiredCapabilities": {}})
    sid = r.get("sessionId") or (r.get("value") or {}).get("sessionId")
    say("session", sid, str(r)[:160])
    say("settings", str(call("POST", S("/appium/settings"), {"settings": {"waitForIdleTimeout": 0, "animationCoolOffTimeout": 0}}))[:160])
    v = call("GET", S("/window/size")).get("value") or {}
    if isinstance(v, dict) and v.get("width"):
        W, H = float(v["width"]), float(v["height"])
    say("window(pt)", W, H)


def tap_pt(x, y):
    """화면 좌표(pt)를 손가락으로 한 번 누른다. 앱 구분 없이 화면 전체에 먹는다."""
    body = {
        "actions": [
            {
                "type": "pointer",
                "id": "finger1",
                "parameters": {"pointerType": "touch"},
                "actions": [
                    {"type": "pointerMove", "duration": 0, "x": int(x), "y": int(y)},
                    {"type": "pointerDown", "button": 0},
                    {"type": "pause", "duration": 120},
                    {"type": "pointerUp", "button": 0},
                ],
            }
        ]
    }
    r = call("POST", S("/actions"), body, timeout=60)
    call("DELETE", S("/actions"), timeout=30)
    if "_http" in r or "_err" in r:
        r = call("POST", S("/wda/tap/0"), {"x": x, "y": y}, timeout=60)
    ok = "_http" not in r and "_err" not in r
    if not ok:
        say("tap_pt failed:", str(r)[:200])
    return ok


def tap_it(it):
    say(f"  tap {it['type']}:{it['label'][:30]!r} at ({it['x'] + it['w'] / 2:.0f},{it['y'] + it['h'] / 2:.0f})")
    return tap_pt(it["x"] + it["w"] / 2, it["y"] + it["h"] / 2)


def src():
    r = call("GET", S("/source"), timeout=90)
    v = r.get("value")
    return v if isinstance(v, str) else ""


def items(xml):
    try:
        root = ET.fromstring(xml.encode("utf-8"))
    except Exception as e:  # noqa: BLE001
        say("xml parse failed:", repr(e)[:120])
        return []
    out = []
    for el in root.iter():
        a = el.attrib
        t = a.get("type", "")
        if not t.startswith("XCUIElementType"):
            continue
        try:
            x, y, w, h = (float(a.get(k) or 0) for k in ("x", "y", "width", "height"))
        except ValueError:
            continue
        out.append(
            {
                "type": t[len("XCUIElementType"):],
                "label": a.get("label") or a.get("name") or a.get("value") or "",
                "vis": a.get("visible") == "true" and w > 0 and h > 0,
                "x": x,
                "y": y,
                "w": w,
                "h": h,
            }
        )
    return out


def onscreen(i):
    return i["w"] > 0 and i["h"] > 0 and 0 <= i["x"] + i["w"] / 2 <= W and 0 <= i["y"] + i["h"] / 2 <= H


def pick(its, types, pred, y0=None, y1=None, loose=False):
    return [
        i
        for i in its
        if (onscreen(i) if loose else i["vis"])
        and i["type"] in types
        and pred(i["label"])
        and (y0 is None or i["y"] >= y0)
        and (y1 is None or i["y"] <= y1)
    ]


def wait_ui(name, finder, timeout=90, every=2.0):
    t0 = time.time()
    its = []
    while time.time() - t0 < timeout:
        its = items(src())
        got = finder(its)
        if got:
            say(f"[{name}] seen after {time.time() - t0:.0f}s: " + str([(g["type"], g["label"][:28], int(g["x"]), int(g["y"])) for g in got][:4]))
            return got, its
        time.sleep(every)
    say(f"[{name}] NOT SEEN after {timeout}s")
    return [], its


def snap(name):
    time.sleep(1.0)
    r = call("GET", S("/screenshot"))
    b = r.get("value")
    if isinstance(b, str):
        (OUT / f"{name}.png").write_bytes(base64.b64decode(b))
    else:
        subprocess.run(["xcrun", "simctl", "io", "booted", "screenshot", str(OUT / f"{name}.png")], check=False)
    xml = src()
    (OUT / f"{name}.xml").write_text(xml, encoding="utf-8")
    its = items(xml)
    labs = []
    for i in its:
        if i["vis"] and i["label"] and i["type"] in ("Button", "StaticText", "Cell", "MenuItem", "Alert", "Sheet"):
            s = f"{i['type']}:{i['label'][:40]}"
            if s not in labs:
                labs.append(s)
    say(f"== {name}: " + " | ".join(labs[:60]))
    return its


def openurl(u):
    subprocess.run(["xcrun", "simctl", "openurl", "booted", u], check=False)
    time.sleep(4)


def terminate(bid):
    call("POST", S("/wda/apps/terminate"), {"bundleId": bid})
    time.sleep(1)


def tips(its):  # 사파리 첫 실행 안내 말풍선 닫기
    for i in its:
        if i["vis"] and i["label"] in ("dismiss popup", "Not Now", "Continue"):
            say("[tips] dismiss", i["label"])
            tap_it(i)
            time.sleep(1)
            return True
    return False


def db_rows(tag):  # 시뮬레이터 연락처 DB에서 샘플이 아닌 사람의 (행번호, 이름, 번호들)을 모두 출력
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
    names = ",".join(f"'{n}'" for n in SAMPLE)
    q = (
        "select p.ROWID, p.First, ifnull(group_concat(v.value, ','), '') from ABPerson p "
        "left join ABMultiValue v on v.record_id = p.ROWID and v.property = 3 "
        f"where p.First not in ({names}) group by p.ROWID order by p.First, p.ROWID;"
    )
    r = subprocess.run(["sqlite3", str(tmp / "AddressBook.sqlitedb"), q], capture_output=True, text=True)
    rows = [x for x in r.stdout.strip().split(chr(10)) if x]
    say(f"DB[{tag}] ({len(rows)} rows): " + " | ".join(rows) + " " + r.stderr.strip()[:200])
    return rows


def warm_contacts():
    """연락처 앱을 미리 켜 둔다. v8에서 연락처 앱이 꺼진 채로 공유 창의 '연락처'를 누르면 앱이 안 열리고 사파리 첫 화면으로 돌아왔다(켜 둔 상태에선 열림)."""
    subprocess.run(["xcrun", "simctl", "launch", "booted", "com.apple.MobileAddressBook"], check=False)
    time.sleep(12)


def open_import_sheet(tag, url):
    """사파리에서 vcf를 열고 공유 -> 연락처까지 눌러 가져오기 화면(오른쪽 위 Save, 머리글 Add All N)을 띄운다."""
    for attempt in (1, 2, 3, 4):
        terminate("com.apple.mobilesafari")
        openurl(url)
        got, its = wait_ui(
            "preview",
            lambda its: pick(its, ("Button", "Cell", "StaticText"), lambda l: l in ("Create New Contact", "Add to Existing Contact") or l.startswith("Update Contact")),
            90,
        )
        if not got:
            snap(f"{tag}-no-preview-{attempt}")
            continue
        tips(its)
        snap(f"{tag}-preview")
        its = items(src())
        share = sorted(pick(its, ("Button",), lambda l: l == "Share"), key=lambda i: i["y"])
        if not share:
            snap(f"{tag}-no-share-{attempt}")
            continue
        tap_it(share[0])
        cs, its = wait_ui("contacts", lambda its: pick(its, ("Cell",), lambda l: l == "Contacts", loose=True), 40)
        if not cs:
            snap(f"{tag}-no-contacts-{attempt}")
            continue
        time.sleep(2)  # 공유 창은 내용이 늦게 차면서 밀린다 -> 자리 잡은 뒤 다시 읽어서 누른다
        cs = pick(items(src()), ("Cell",), lambda l: l == "Contacts", loose=True) or cs
        tap_it(cs[min(PICK, len(cs) - 1)])
        got, its = wait_ui(
            "import-ui",
            lambda its: [i for i in its if i["vis"] and i["type"] == "Button" and i["label"] == "Save" and i["y"] < H * 0.3],
            45,
        )
        if got:
            return its
        snap(f"{tag}-no-import-ui-{attempt}")
        warm_contacts()  # 다음 시도 전에 연락처 앱을 켜 둔다
    return None


def sheet_buttons(its):  # 화면 아래쪽 확인창의 버튼들(취소 제외). 맨 아래 Cancel이 같이 보일 때만 확인창으로 본다(연락처 목록의 Add 버튼을 누르지 않게)
    bottom = [i for i in its if i["vis"] and i["type"] in ("Button", "MenuItem") and i["y"] > H * 0.35 and i["label"]]
    if not any(b["label"] == "Cancel" for b in bottom):
        return []
    return [b for b in bottom if b["label"] != "Cancel"]


def sheet_text(its):
    return [i["label"] for i in its if i["vis"] and i["type"] == "StaticText" and i["y"] > H * 0.35 and i["label"]]


def run_import(tag, url, mode):
    """mode: save(오른쪽 위 Save) | addall(머리글 Add All -> Add All -> 확인창) | create(머리글 -> Create New Contacts)"""
    its = open_import_sheet(tag, url)
    if its is None:
        say(f"[{tag}] FAILED: import sheet never opened")
        return False
    snap(f"{tag}-import-sheet")
    if mode == "save":
        tap_it([i for i in its if i["vis"] and i["type"] == "Button" and i["label"] == "Save"][0])
        time.sleep(6)
        snap(f"{tag}-after")
        return True
    hdr = [i for i in its if i["vis"] and i["label"].startswith("Add All") and i["y"] < H * 0.45]
    if not hdr:
        say(f"[{tag}] FAILED: header 'Add All N Contacts' not found")
        return False
    tap_it(hdr[0])
    time.sleep(2)
    want = "Create New Contacts" if mode == "create" else "Add All"
    got, _ = wait_ui("options", lambda its: pick(its, ("Button", "MenuItem", "Cell"), lambda l: l.startswith(want), y0=H * 0.35), 15)
    snap(f"{tag}-options")
    if not got:
        say(f"[{tag}] FAILED: option {want!r} not found")
        return False
    tap_it(sorted(got, key=lambda i: i["y"])[-1])
    for step in range(1, 4):  # 뜨는 확인창을 끝까지 따라간다
        time.sleep(2.5)
        its3 = snap(f"{tag}-step{step}")
        btns = sheet_buttons(its3)
        say(f"[{tag}] step{step} text={sheet_text(its3)[:4]} buttons={[b['label'] for b in btns]}")
        todo = [b for k in PREFER for b in btns if b["label"].startswith(k)]
        if not todo:
            break
        tap_it(todo[0])
    time.sleep(5)
    snap(f"{tag}-after")
    return True


def main():
    db_rows("00-before")
    warm_contacts()
    # 사람 묶음을 따로 써서 앞선 시험이 뒤 시험을 어지럽히지 않게 한다(g1 = Save 묶음, g2 = Add All 묶음)
    plan = [
        ("S1-save", SITE + "g1.vcf", "save"),                 # 빈 상태에서 2명 Save -> 2명 생기나
        ("S2-save-again", SITE + "g1.vcf", "save"),           # 같은 2명을 Save로 다시 -> 사람이 또 생기나(중복)
        ("H1-addall", SITE + "g2.vcf", "addall"),             # 빈 상태에서 2명 Add All -> 'did not match' 확인창 -> Create New Contacts
        ("H2-addall-again", SITE + "g2.vcf", "addall"),       # 같은 2명을 Add All로 다시 -> 사람이 또 생기나, 번호가 또 붙나
        ("H3-samename", SITE + "g2n.vcf", "addall"),          # 같은 이름·다른 번호 + 새 사람
        ("H4-samenum", SITE + "g2p.vcf", "addall"),           # 다른 이름·같은 번호 + 새 사람
    ]
    for tag, url, mode in plan:
        say(f"##### {tag}: {mode} {url}")
        run_import(tag, url, mode)
        db_rows(f"after-{tag}")


if __name__ == "__main__":
    subprocess.run("sw_vers; xcrun simctl list devices booted; xcrun simctl list runtimes", shell=True, check=False)
    say("PICK", PICK)
    session()
    try:
        main()
    except Exception as e:  # noqa: BLE001
        say("ERROR", repr(e))
    say("done")
