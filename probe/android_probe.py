"""안드로이드 에뮬레이터에서 '페이지 저장 -> 파일 받기 -> 연락처로 가져오기'를 눌러 보고 연락처 수를 센다. 가짜 명단만 다룬다.
adb 만 쓴다(uiautomator dump 로 화면을 읽고 input tap 으로 누른다). 한 단계가 안 돼도 다음 단계는 계속한다.
단계: ① 크롬으로 페이지를 열고 '저장'을 눌러 파일이 받아지나 ② 받은 파일을 '열기'(VIEW 인텐트)로 연락처 앱에 넘겨 가져오기 ③ 연락처 수 세기 ④ 같은 파일을 한 번 더 가져오면 중복이 생기나"""
import os
import pathlib
import re
import subprocess
import time
import xml.etree.ElementTree as ET

OUT = pathlib.Path(os.environ.get("OUT", "shots"))
OUT.mkdir(parents=True, exist_ok=True)
SLUG = os.environ["SLUG"]
HOST = "http://10.0.2.2:8000"
LOG = open(OUT / "log.txt", "w", encoding="utf-8")
FRE_BUTTONS = ("Accept & continue", "No thanks", "Use without an account", "Got it", "Not now", "Skip", "No, thanks", "Continue", "수락 및 계속", "사용 안함")
IMPORT_BUTTONS = ("OK", "확인", "Import", "IMPORT", "가져오기", "Phone", "Device", "DEVICE", "Device only", "Local", "Save", "SAVE", "Done", "Allow", "ALLOW", "While using the app", "Only this time", "Contacts", "Google Contacts", "Just once", "JUST ONCE", "Always", "ALWAYS", "Next", "NEXT", "Continue")


def say(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    LOG.write(s + "\n")
    LOG.flush()


def adb(*a, timeout=90):
    r = subprocess.run(["adb", *a], capture_output=True, text=True, timeout=timeout)
    return (r.stdout or "") + (r.stderr or "")


def sh(cmd, timeout=90):
    return adb("shell", cmd, timeout=timeout)


def shot(name):
    with open(OUT / f"{name}.png", "wb") as f:
        subprocess.run(["adb", "exec-out", "screencap", "-p"], stdout=f, check=False, timeout=60)


def dump(name=None):
    sh("uiautomator dump /sdcard/ui.xml")
    xml = adb("exec-out", "cat", "/sdcard/ui.xml")
    xml = xml[xml.find("<?xml"):] if "<?xml" in xml else xml
    if name:
        (OUT / f"{name}.xml").write_text(xml, encoding="utf-8")
    return xml


def nodes(xml):
    out = []
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return out
    for n in root.iter("node"):
        m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", n.get("bounds", ""))
        if not m:
            continue
        l, t, r, b = map(int, m.groups())
        out.append({"text": n.get("text") or "", "desc": n.get("content-desc") or "", "id": n.get("resource-id") or "", "pkg": n.get("package") or "",
                    "cls": n.get("class") or "", "click": n.get("clickable") == "true", "box": (l, t, r, b)})
    return out


def label(n):
    return n["text"] or n["desc"]


def tap(n):
    l, t, r, b = n["box"]
    say(f"  tap {label(n)!r} [{n['pkg']}] at ({(l + r) // 2},{(t + b) // 2})")
    sh(f"input tap {(l + r) // 2} {(t + b) // 2}")


def screen(name):
    """화면 캡처 + 보이는 글자 한 줄 요약."""
    shot(name)
    xml = dump(name)
    labs = [label(n) for n in nodes(xml) if label(n)]
    say(f"== {name}: " + " | ".join(dict.fromkeys(labs))[:900])
    return xml


def count(tag):
    con = sh("content query --uri content://com.android.contacts/contacts --projection display_name")
    raw = sh("content query --uri content://com.android.contacts/raw_contacts --projection display_name")
    ph = sh("content query --uri content://com.android.contacts/data/phones --projection display_name:data1")
    nc, nr = len(re.findall(r"^Row:", con, re.M)), len(re.findall(r"^Row:", raw, re.M))
    names = sorted(re.findall(r"display_name=(.*?)(?:,|$)", con, re.M))
    phones = re.findall(r"data1=(\S+)", ph)
    say(f"CONTACTS[{tag}] contacts={nc} raw_contacts={nr} phones={len(phones)} names={names}")
    return nc, nr


def logcat(tag):
    out = adb("logcat", "-d", "-t", "4000")
    keep = [l for l in out.splitlines() if re.search(r"vcard|importvcard|VCardImport|ContactsProvider|contacts.*(import|error|exception)", l, re.I)]
    say(f"LOGCAT[{tag}] ({len(keep)} lines):")
    for l in keep[-25:]:
        say("   ", l[:240])
    adb("logcat", "-c")


def press_any(buttons, tag, seconds=40):
    """보이는 버튼 중 목록에 있는 것을 누르며 화면이 바뀌길 기다린다."""
    t0 = time.time()
    while time.time() - t0 < seconds:
        xml = dump()
        hit = [n for n in nodes(xml) if label(n) in buttons and n["pkg"] != "com.android.systemui"]
        if not hit:
            return True
        screen(f"{tag}-{int(time.time() - t0)}s")
        tap(hit[0])
        time.sleep(3)
    return False


def main():
    say(adb("root").strip())
    time.sleep(2)
    say("android", sh("getprop ro.build.version.release").strip(), "sdk", sh("getprop ro.build.version.sdk").strip(), sh("getprop ro.product.model").strip())
    pk = sh("pm list packages")
    say("packages:", [p for p in pk.split() if re.search(r"chrome|browser|contacts|documentsui|downloads|vending|samsung", p, re.I)])
    sh("settings put global window_animation_scale 0; settings put global transition_animation_scale 0; settings put global animator_duration_scale 0")
    count("00-before")

    # ① 크롬으로 페이지를 열고 '저장'을 눌러 본다 (크롬 첫 실행 안내를 건너뛰는 명령줄 파일)
    chrome = "package:com.android.chrome" in pk
    if chrome:
        sh("echo 'chrome --disable-fre --no-default-browser-check --no-first-run' > /data/local/tmp/chrome-command-line; chmod 755 /data/local/tmp/chrome-command-line; am set-debug-app --persistent com.android.chrome")
        sh("rm -rf /sdcard/Download/*")
        say(sh(f'am start -a android.intent.action.VIEW -d "{HOST}/{SLUG}/?me=1" com.android.chrome').strip()[:200])
        time.sleep(12)
        saved = False
        for i in range(8):
            xml = screen(f"1-chrome-{i}")
            hit = [n for n in nodes(xml) if re.fullmatch(r"\d+명 저장", label(n))]
            if hit:
                tap(hit[0])
                saved = True
                break
            fre = [n for n in nodes(xml) if label(n) in FRE_BUTTONS]
            if fre:
                tap(fre[0])
            time.sleep(4)
        adb("logcat", "-c")
        for i in range(10):  # 받기가 끝나면 화면 위에 'File downloaded ... Open' 배너가 뜬다
            time.sleep(1.5)
            xml = dump()
            op = [n for n in nodes(xml) if label(n) in ("Open", "열기") and n["pkg"] == "com.android.chrome"]
            if op:
                screen("1-after-save-tap")
                tap(op[0])
                say("chrome 'Open' tapped")
                break
        else:
            screen("1-after-save-tap")
        time.sleep(6)
        screen("1-after-open-tap")
        press_any(IMPORT_BUTTONS, "1-open", 45)
        time.sleep(6)
        screen("1-after-open-end")
        count("after-chrome-open")
        logcat("after-chrome-open")
        say("saved tapped:", saved, "| Downloads:", sh("ls -l /sdcard/Download").strip().replace("\n", " ; ")[:300])
    else:
        say("chrome: 없음 -> 파일을 직접 밀어 넣는다")

    # 받아진 파일이 없으면 러너의 사이트에서 직접 받아 넣는다(브라우저 단계만 건너뜀)
    files = [f for f in sh("ls /sdcard/Download").split() if f.endswith(".vcf")]
    if not files:
        say("받은 파일 없음 -> m/1.vcf 를 adb push")
        subprocess.run(["adb", "push", f"site/{SLUG}/m/1.vcf", "/sdcard/Download/m1.vcf"], check=False)
        sh("am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d file:///sdcard/Download/m1.vcf")
        files = ["m1.vcf"]
    fname = files[0]
    say("import file:", fname, sh(f"ls -l '/sdcard/Download/{fname}'").strip())

    # ② '열기': 다운로드 알림의 '열기'는 파일의 content:// 주소를 MIME(text/x-vcard)과 함께 VIEW 로 넘긴다
    q = sh("content query --uri content://media/external/downloads --projection _id:_display_name")
    say("downloads:", q.strip().replace("\n", " ; ")[:400])
    m = re.search(r"_id=(\d+), _display_name=" + re.escape(fname), q)
    uri = f"content://media/external/downloads/{m.group(1)}" if m else f"file:///sdcard/Download/{fname}"
    say("open uri:", uri)

    def open_and_import(tag):
        sh("input keyevent KEYCODE_HOME")
        out = sh(f"am start -a android.intent.action.VIEW -t text/x-vcard -d '{uri}' --grant-read-uri-permission")
        say(f"[{tag}] am start:", out.strip().replace("\n", " ")[:300])
        time.sleep(6)
        screen(f"2-{tag}-first")
        press_any(IMPORT_BUTTONS, f"2-{tag}", 60)
        time.sleep(8)
        screen(f"2-{tag}-end")
        r = count(f"after-{tag}")
        logcat(tag)
        return r

    a = open_and_import("import1")
    b = open_and_import("import2-same-file")  # ④ 같은 파일을 한 번 더
    say(f"RESULT first import: contacts={a[0]} raw={a[1]} | second import: contacts={b[0]} raw={b[1]}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        say("ERROR", repr(e))
    say("done")
