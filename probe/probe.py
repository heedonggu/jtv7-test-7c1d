"""iOS 시뮬레이터 사파리에서 'vcf 여러 명 저장' 화면을 실제로 눌러 보고 연락처 DB를 직접 센다.
WebDriverAgent(8100) HTTP API만 쓴다. 가짜 명단만 다룬다.
(v7: 같은 파일 재가져오기·같은 이름 다른 번호·다른 이름 같은 번호를 'Save' / 'Create New Contacts' / 'Add All N Contacts'로 비교)"""
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
SITE = f"http://localhost:8000/"
BASE = SITE + f"{os.environ['SLUG']}/"
PICK = int(os.environ.get("PICK", "0"))  # 공유 시트의 'Contacts' 두 개 중 몇 번째를 누를지
LOG = open(OUT / "log.txt", "w", encoding="utf-8")
sid = None
BSL = chr(92)  # 역슬래시 (정규식 이스케이프 오타 방지)
LABEL_RE = re.compile(r"<XCUIElementType(" + BSL + r"w+)[^>]*?" + BSL + r'blabel="([^"]*)"')
SAMPLE = ("Anna", "Daniel", "David", "Hank", "John", "Kate")


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


def terminate(bid):
    call("POST", S("/wda/apps/terminate"), {"bundleId": bid})
    time.sleep(1)


def tips():  # 사파리 첫 실행 안내 말풍선 닫기
    for p in ("label == 'dismiss popup'", "label == 'Not Now'", "label == 'Continue'"):
        if tap(p):
            say("[tips] dismissed via", p)
            time.sleep(1)


def db_rows(tag):  # 시뮬레이터 연락처 DB에서 샘플이 아닌 사람의 (이름, 번호)를 모두 출력
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
        "select p.First, ifnull(group_concat(v.value, ','), '') from ABPerson p "
        "left join ABMultiValue v on v.record_id = p.ROWID and v.property = 3 "
        f"where p.First not in ({names}) group by p.ROWID order by p.First, p.ROWID;"
    )
    r = subprocess.run(["sqlite3", str(tmp / "AddressBook.sqlitedb"), q], capture_output=True, text=True)
    rows = [x for x in r.stdout.strip().split(chr(10)) if x]
    say(f"DB[{tag}] ({len(rows)} rows): " + " | ".join(rows) + " " + r.stderr.strip()[:200])
    return rows


def button_labels(xml):
    return [label for t, label in LABEL_RE.findall(xml) if t in ("Button", "MenuItem", "Cell") and label]


def import_file(tag, url, mode):
    """vcf 주소를 사파리로 열고 공유 -> 연락처 -> (mode)로 저장. mode: save | create | addall"""
    for attempt in (1, 2):
        terminate("com.apple.mobilesafari")
        openurl(url)
        if not wait_for("preview", ["label == 'Create New Contact'", "label BEGINSWITH 'Update Contact'", "label == 'Add to Existing Contact'"], 90):
            snap(f"{tag}-no-preview-{attempt}")
            continue
        tips()
        snap(f"{tag}-preview")
        if not wait_tap("share", ["label == 'Share'"], 20):
            snap(f"{tag}-no-share-{attempt}")
            continue
        if not wait_tap("contacts", ["type == 'XCUIElementTypeCell' AND label == 'Contacts'"], 15, n=PICK):
            continue
        if not wait_for("import-ui", ["label == 'Save'"], 120):
            snap(f"{tag}-no-import-ui-{attempt}")
            continue
        xml = snap(f"{tag}-import-sheet")
        m = re.search(r"Add All (" + BSL + r"d+) Contacts", xml)
        say("IMPORT-SHEET title:", m.group(0) if m else None)
        if mode == "save":
            wait_tap("save", ["label == 'Save'"], 10)
        else:
            if not wait_tap("header", ["label BEGINSWITH 'Add All'"], 10):
                continue
            xml2 = snap(f"{tag}-header-options")
            say("HEADER-OPTIONS:", [x for x in button_labels(xml2) if x not in ("Cancel",)][:12])
            want = "Create New Contacts" if mode == "create" else "Add All"
            ok = wait_tap(
                "option",
                [f"(type == 'XCUIElementTypeButton' OR type == 'XCUIElementTypeCell' OR type == 'XCUIElementTypeMenuItem') AND label BEGINSWITH '{want}'"],
                10,
            )
            if not ok:
                continue
        time.sleep(4)
        snap(f"{tag}-after")
        return True
    say(f"[import_file {tag}] FAILED after retries")
    return False


def main():
    db_rows("00-before")
    plan = [
        ("A-m2-save", BASE + "m/2.vcf", "save"),            # 처음 5명(깨끗한 상태)
        ("B-m2-addall", BASE + "m/2.vcf", "addall"),        # 같은 5명을 'Add All'로 다시 -> 중복이 안 생기나
        ("C-samename-addall", SITE + "t_samename.vcf", "addall"),  # 같은 이름·다른 번호 + 새 사람
        ("D-samenum-addall", SITE + "t_samenum.vcf", "addall"),    # 다른 이름·같은 번호 + 새 사람
        ("E-m2-create", BASE + "m/2.vcf", "create"),        # 같은 5명을 'Create New Contacts'로 -> 비교용(중복 생김)
    ]
    for tag, url, mode in plan:
        say(f"##### {tag}: {mode} {url}")
        import_file(tag, url, mode)
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
