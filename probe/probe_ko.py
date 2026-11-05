"""한국어 아이폰 화면 확인용(v1). 라벨 글자에 기대지 않고 '위치'로 누른다 -> 어느 언어든 같은 흐름이 돈다.
probe.py의 도구(WDA 호출·XML 읽기·DB 세기)를 그대로 쓴다. 가짜 명단만 다룬다.
흐름: 사파리에서 vcf -> 오른쪽 위 공유 -> 연락처 -> (save) 오른쪽 위 저장 / (addall) 머리글 -> 아래에서 두 번째 선택지 -> 뜨는 확인창의 첫 버튼
각 단계 화면을 저장해서 한국어 글자를 그대로 확인한다."""
import time

import probe as P

CANCEL = ("Cancel", "취소")
DONE = ("Done", "완료")
CONTACTS = ("Contacts", "연락처")


def top_right(its):
    return sorted([i for i in its if i["vis"] and i["type"] == "Button" and i["x"] > P.W * 0.75 and i["y"] < P.H * 0.2], key=lambda i: i["y"])


def bottom_buttons(its):  # 화면 아래쪽 선택창 버튼(위에서 아래 순서)
    return sorted([i for i in its if i["vis"] and i["type"] in ("Button", "MenuItem") and i["y"] > P.H * 0.35 and i["label"]], key=lambda i: i["y"])


def import_sheet_open(its):  # 왼쪽 위 취소 + 오른쪽 위 버튼이 같이 보이면 가져오기 화면
    left = [i for i in its if i["vis"] and i["type"] == "Button" and i["label"] in CANCEL and i["x"] < P.W * 0.3 and i["y"] < P.H * 0.2]
    return top_right(its) if left else []


def open_sheet(tag, url):
    for attempt in (1, 2, 3, 4):
        P.terminate("com.apple.mobilesafari")
        P.openurl(url)
        got, its = P.wait_ui(
            "preview",
            lambda its: [i for i in its if i["vis"] and i["type"] == "Button" and i["label"] in DONE and i["x"] < P.W * 0.3 and i["y"] < P.H * 0.2] and top_right(its),
            90,
        )
        if not got:
            P.snap(f"{tag}-no-preview-{attempt}")
            continue
        P.tips(its)
        P.snap(f"{tag}-1-preview")
        P.tap_it(top_right(items_now())[0])
        cs, its = P.wait_ui("contacts", lambda its: P.pick(its, ("Cell",), lambda l: l in CONTACTS, loose=True), 40)
        P.snap(f"{tag}-2-sharesheet")
        if not cs:
            continue
        time.sleep(2)  # 공유 창은 내용이 늦게 차면서 밀린다
        cs = P.pick(items_now(), ("Cell",), lambda l: l in CONTACTS, loose=True) or cs
        P.tap_it(cs[min(P.PICK, len(cs) - 1)])
        got, its = P.wait_ui("import-ui", import_sheet_open, 45)
        if got:
            time.sleep(1)
            P.snap(f"{tag}-3-importsheet")
            return items_now()
        P.snap(f"{tag}-no-import-ui-{attempt}")
        P.warm_contacts()
    return None


def items_now():
    return P.items(P.src())


def run(tag, url, mode):
    its = open_sheet(tag, url)
    if its is None:
        P.say(f"[{tag}] FAILED: import sheet never opened")
        return
    tr = top_right(its)
    if mode == "save":
        P.tap_it(tr[0])
        time.sleep(6)
        P.snap(f"{tag}-after")
        return
    hdr = sorted(
        [i for i in its if i["vis"] and i["type"] == "StaticText" and P.H * 0.12 < i["y"] < P.H * 0.3 and i["label"]],
        key=lambda i: -i["w"],
    )
    if not hdr:
        P.say(f"[{tag}] FAILED: header not found")
        return
    P.say(f"[{tag}] header text: {hdr[0]['label']!r}")
    P.tap_it(hdr[0])
    time.sleep(2.5)
    its = P.snap(f"{tag}-4-options")
    bb = bottom_buttons(its)
    P.say(f"[{tag}] options: {[b['label'] for b in bb]}")
    non_cancel = [b for b in bb if b["label"] not in CANCEL][:2]  # [새로 만들기, 모두 추가] 순서
    if len(non_cancel) < 2:
        P.say(f"[{tag}] FAILED: expected 2 options")
        return
    P.tap_it(non_cancel[1 if mode == "addall" else 0])
    for step in range(1, 4):
        time.sleep(2.5)
        its = P.snap(f"{tag}-5-step{step}")
        allb = bottom_buttons(its)
        bb = [b for b in allb if b["label"] not in CANCEL] if any(b["label"] in CANCEL for b in allb) else []
        txt = [i["label"] for i in its if i["vis"] and i["type"] == "StaticText" and i["y"] > P.H * 0.35 and i["label"]]
        P.say(f"[{tag}] step{step} text={txt[:4]} buttons={[b['label'] for b in bb]}")
        if not bb:
            break
        P.tap_it(bb[0])
    time.sleep(5)
    P.snap(f"{tag}-6-after")


if __name__ == "__main__":
    import subprocess

    subprocess.run("sw_vers; xcrun simctl list devices booted; defaults read -g AppleLanguages 2>/dev/null | head -3", shell=True, check=False)
    P.session()
    try:
        P.db_rows("00-before")
        P.warm_contacts()
        for tag, url, mode in [
            ("KA-m2-addall", P.BASE + "m/2.vcf", "addall"),
            ("KB-m2-addall-again", P.BASE + "m/2.vcf", "addall"),
            ("KC-m2-save", P.BASE + "m/2.vcf", "save"),
        ]:
            P.say(f"##### {tag}: {mode} {url}")
            run(tag, url, mode)
            P.db_rows(f"after-{tag}")
    except Exception as e:  # noqa: BLE001
        P.say("ERROR", repr(e))
    P.say("done")
