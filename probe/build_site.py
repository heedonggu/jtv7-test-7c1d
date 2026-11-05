"""명단 xlsx -> 배포용 정적 사이트. 사용: build_site.py <명단.xlsx> <site폴더>
사람마다 '본인을 뺀' 연락처 파일(m/<번호>.vcf)을 만든다. 페이지에서는 그 55명 중 저장할 사람을 고를 수 있다.
site 안에 폴더가 이미 있으면 그 이름(slug)을 그대로 쓴다 - 주소가 바뀌면 이미 뿌린 링크가 죽는다."""
import html
import re
import secrets
import shutil
import sys
import unicodedata
from pathlib import Path

import openpyxl

src, site = Path(sys.argv[1]), Path(sys.argv[2])
ORG = "JTV 7기"
GROUP = "윤자동이 실현하는거 우리도 해보자 모임"

old = [d.name for d in site.iterdir() if d.is_dir()] if site.exists() else []
assert len(old) <= 1, f"site 안 폴더가 둘 이상: {old}"
slug = old[0] if old else secrets.token_hex(8)

ws = openpyxl.load_workbook(src, data_only=True).active
rows, bad = [], []
for no, name, tel, *_ in ws.iter_rows(values_only=True):
    if no is None:  # 제목줄·빈 줄
        continue
    if isinstance(tel, float):
        tel = int(tel)
    d = re.sub(r"\D", "", str(tel))
    if len(d) == 10 and d.startswith("10"):  # 엑셀이 앞자리 0을 떼먹은 경우
        d = "0" + d
    name = unicodedata.normalize("NFC", re.sub(r"\s+", " ", str(name or ""))).strip()
    if not name or not re.fullmatch(r"010\d{8}", d):
        bad.append((no, name, tel))
        continue
    rows.append((int(no), name, f"{d[:3]}-{d[3:7]}-{d[7:]}"))

assert not bad, f"변환 불가 행: {bad}"
assert len(rows) == ws.max_row - 1, f"행 누락: {len(rows)} vs {ws.max_row - 1}"
assert len({t for _, _, t in rows}) == len(rows), "전화번호 중복"
assert len({n for n, _, _ in rows}) == len(rows), "명단 번호 중복"


def esc(s):
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


# ponytail: 이름은 성/이름 분리 안 함(남궁·선우 오분리 방지), 줄 접기 없음(아래 검사가 75바이트 한도 감시)
def card(name, tel):
    return "\r\n".join([
        "BEGIN:VCARD", "VERSION:3.0", f"N:;{esc(name)};;;", f"FN:{esc(name)}",
        f"ORG:{esc(ORG)}", f"CATEGORIES:{esc(ORG)}", f"TEL;TYPE=CELL:{tel}",
        f"NOTE:{esc(GROUP)}", "END:VCARD", ""])


out = site / slug
shutil.rmtree(out, ignore_errors=True)  # 이전 빌드 산출물 정리(줄어든 명단의 옛 파일이 남지 않게)
(out / "m").mkdir(parents=True)
for no, name, tel in rows:
    raw = "".join(card(n, t) for k, n, t in rows if k != no).encode("utf-8")
    assert raw.startswith(b"BEGIN:VCARD\r\nVERSION:3.0\r\n"), "BOM/헤더 이상"
    assert b"\n" not in raw.replace(b"\r\n", b""), "CRLF 아닌 줄바꿈"
    assert all(len(l) <= 75 for l in raw.split(b"\r\n")), "75바이트 초과 줄(접기 필요)"
    assert raw.count(b"BEGIN:VCARD") == raw.count(b"END:VCARD") == len(rows) - 1, "카드 수 불일치"
    assert tel.encode() not in raw, f"본인 번호가 들어감: {name}"
    (out / "m" / f"{no}.vcf").write_bytes(raw)

PAGE = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>JTV 7기 연락처 저장</title>
<meta property="og:title" content="JTV 7기 연락처 저장">
<meta property="og:description" content="내 이름을 고르면 나를 뺀 연락처를 골라서 저장할 수 있어요">
<meta property="og:type" content="website">
<style>
:root{--bg:#f6f7f9;--card:#fff;--ink:#14171c;--sub:#5b6472;--line:#e3e6ea;--accent:#2563eb;--on-accent:#fff}
@media (prefers-color-scheme:dark){:root{--bg:#0e1013;--card:#171a1f;--ink:#eef0f3;--sub:#9aa3b0;--line:#272c34;--accent:#5b8def;--on-accent:#0b1020}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.6 -apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Noto Sans KR","Malgun Gothic",sans-serif;-webkit-text-size-adjust:100%;word-break:keep-all;overflow-wrap:break-word}
main{max-width:440px;margin:0 auto;padding:40px 16px 56px}
.tag{display:inline-block;padding:2px 10px;border:1px solid var(--line);border-radius:999px;font-size:13px;color:var(--sub)}
h1{margin:14px 0 6px;font-size:28px;line-height:1.25;letter-spacing:-.02em}
.lead{margin:0 0 16px;color:var(--sub)}
.names{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}
.name{display:flex;align-items:center;justify-content:center;min-height:48px;padding:0 4px;border:1px solid var(--line);border-radius:12px;background:var(--card);color:var(--ink);font-size:16px;font-weight:600;text-decoration:none}
.name:active{background:var(--accent);border-color:var(--accent);color:var(--on-accent)}
.name:focus-visible{outline:3px solid var(--ink);outline-offset:2px}
.q{width:100%;min-height:52px;margin:0 0 12px;padding:0 16px;border:1px solid var(--line);border-radius:12px;background:var(--card);color:var(--ink);font:inherit;font-size:17px}
.q:focus-visible{outline:3px solid var(--accent);outline-offset:1px}
.after{margin:0 0 16px;padding:12px 14px;border:1px solid var(--line);border-radius:12px;background:var(--card);font-size:15px;color:var(--sub)}
.after p{margin:4px 0}
.after b{color:var(--ink)}
.after ol{margin:2px 0 8px;padding-left:22px}
.after li{margin:3px 0}
.ico{vertical-align:-4px}
.bar{display:flex;align-items:center;gap:8px;margin:0 0 10px}
.bar button{min-height:40px;padding:0 14px;border:1px solid var(--line);border-radius:10px;background:var(--card);color:var(--ink);font:inherit;font-size:15px}
.bar span{margin-left:auto;color:var(--sub);font-size:15px}
.picks{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:0 0 18px;color:var(--sub)}
.pick{display:flex;align-items:center;gap:6px;min-height:44px;padding:0 8px;border:1px solid var(--line);border-radius:10px;background:var(--card);color:var(--ink);font-size:15px}
.pick input{width:18px;height:18px;margin:0;flex:none}
.how{margin:28px 0 0;padding:0;list-style:none;display:grid;gap:10px}
.how li{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.how b{display:block;margin-bottom:2px}
.how span{color:var(--sub);font-size:15px}
.note{margin:22px 0 0;color:var(--sub);font-size:14px}
.kakao-note{display:none;margin:0 0 20px;padding:12px 14px;border-radius:12px;background:var(--card);border:1px solid var(--accent);font-size:15px}
.kakao .kakao-note{display:block}
.btn{display:flex;align-items:center;justify-content:center;min-height:60px;border-radius:14px;background:var(--accent);color:var(--on-accent);font-size:19px;font-weight:700;text-decoration:none}
.btn:active{opacity:.85}
.btn[aria-disabled=true]{background:var(--line);color:var(--sub);pointer-events:none}
#save{position:sticky;bottom:12px;z-index:2;box-shadow:0 6px 24px rgba(0,0,0,.28)}
[hidden]{display:none!important}
</style>
</head>
<body>
<main>
  <span class="tag">JTV 7기</span>
  <h1>연락처 한 번에 저장</h1>
  <p class="kakao-note">카카오톡 안에서는 저장이 막힐 수 있어요. 기본 브라우저가 자동으로 안 열리면, 아이폰은 공유 버튼 → Safari로 열기, 안드로이드는 ⋮ → 다른 브라우저로 열기를 눌러 주세요.</p>
  <section id="mine" hidden>
    <p class="lead"><b id="who"></b>님, 나를 뺀 @COUNT@명이에요. 빼고 싶은 사람이나 이미 저장해 둔 사람은 체크를 끄고, 맨 아래 “저장”을 누르세요.</p>
    <div class="after">
      <p><b>아이폰</b> (Safari에서 열어야 해요)</p>
      <ol>
        <li>“저장”을 누르세요. 첫 사람 한 명만 보이는 화면이 떠요. 정상이에요.</li>
        <li>그 화면 <b>오른쪽 위</b> 공유 버튼 <svg class="ico" width="20" height="20" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v12M8 7l4-4 4 4M7 11H5.5a1 1 0 0 0-1 1v8a1 1 0 0 0 1 1h13a1 1 0 0 0 1-1v-8a1 1 0 0 0-1-1H17" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg> 을 누르세요.</li>
        <li>뜨는 창에서 <b>“연락처”</b>를 누르세요. “연락처”가 두 곳(위 아이콘 줄, 아래 목록)에 있으면 한쪽이 안 될 때 다른 쪽을 누르세요.</li>
        <li>고른 사람 목록 화면이 뜨면 <b>오른쪽 위 “저장”</b>을 누르세요. 그러면 한꺼번에 저장돼요.</li>
      </ol>
      <p><b>안드로이드</b> “저장”을 누르고 알림의 “열기” → 저장할 계정을 고르세요.</p>
    </div>
    <div class="bar"><button type="button" id="all">모두 선택</button><button type="button" id="none">모두 해제</button><span id="cnt"></span></div>
    <div class="picks" id="picks">불러오는 중…</div>
    <a class="btn" id="save" href="./">저장</a>
    <p class="note"><a href="./">내 이름이 아니에요</a></p>
  </section>
  <div id="list">
    <p class="lead">내 이름을 입력하거나 누르세요. 나를 뺀 @COUNT@명 중에서 골라 저장할 수 있어요.</p>
    <input id="q" class="q" type="search" placeholder="내 이름 입력" autocomplete="off" aria-label="내 이름 입력">
    <p id="nomatch" class="note" hidden>일치하는 이름이 없어요.</p>
    <nav class="names" aria-label="내 이름 선택">
@NAMES@
    </nav>
    <ul class="how">
      <li><b>아이폰</b><span>Safari에서 이름을 누르고 “저장” → 한 명만 보이는 화면 오른쪽 위 공유 버튼 → “연락처” → 오른쪽 위 “저장”.</span></li>
      <li><b>안드로이드</b><span>이름을 누르고 “저장” → 알림의 “열기” → 저장할 계정 고르기.</span></li>
    </ul>
    <p class="note">저장한 뒤 연락처에서 “JTV 7기”로 검색하면 나와요.</p>
    <p class="note">이 링크는 JTV 7기 단톡방 전용이에요. 밖으로 공유하지 말아 주세요.</p>
  </div>
</main>
<script>
(function () {
  if (/KAKAOTALK/i.test(navigator.userAgent)) {
    document.documentElement.classList.add('kakao');
    location.href = 'kakaotalk://web/openExternal?url=' + encodeURIComponent(location.href);
    return;
  }
  var $ = function (id) { return document.getElementById(id); };
  var items = Array.prototype.slice.call(document.querySelectorAll('a.name'));
  var cards = [], boxes = [];

  $('q').addEventListener('input', function () {  // 이름을 입력하면 맞는 이름만 남긴다
    var v = $('q').value.replace(/\\s+/g, ''), n = 0;
    items.forEach(function (a) { var ok = !v || a.textContent.indexOf(v) !== -1; a.hidden = !ok; if (ok) n++; });
    $('nomatch').hidden = n > 0;
  });
  items.forEach(function (a) { a.addEventListener('click', function (e) { e.preventDefault(); show(a); }); });

  function show(a) {  // 내 이름을 고르면 나를 뺀 사람들을 체크 목록으로 보여 준다
    $('who').textContent = a.textContent;
    $('save').href = a.href;
    $('save').setAttribute('download', 'JTV7기.vcf');  // 아이폰은 vcf 링크를 그냥 열면 첫 사람만 보이는 미리보기(공유 버튼 없음)라 파일로 받게 한다
    $('list').hidden = true;
    $('mine').hidden = false;
    $('picks').textContent = '불러오는 중…';
    cards = []; boxes = [];
    window.scrollTo(0, 0);
    fetch(a.href).then(function (r) { return r.text(); }).then(function (t) {
      cards = t.split(/(?=BEGIN:VCARD)/).filter(function (c) { return /BEGIN:VCARD/.test(c); });
      $('picks').textContent = '';
      cards.forEach(function (c) {
        var l = document.createElement('label'), b = document.createElement('input'), s = document.createElement('span');
        l.className = 'pick'; b.type = 'checkbox'; b.checked = true; b.addEventListener('change', count);
        s.textContent = (c.match(/^FN:(.*?)\\r?$/m) || [])[1] || '';
        l.appendChild(b); l.appendChild(s); $('picks').appendChild(l); boxes.push(b);
      });
      count();
    }).catch(function () { $('picks').textContent = '목록을 못 불러왔어요. 저장을 누르면 전원이 저장돼요.'; });
  }
  function count() {
    var n = boxes.filter(function (b) { return b.checked; }).length;
    $('cnt').textContent = n + '명 선택';
    $('save').textContent = n ? n + '명 저장' : '고른 사람이 없어요';
    $('save').setAttribute('aria-disabled', n ? 'false' : 'true');
  }
  function setAll(v) { boxes.forEach(function (b) { b.checked = v; }); count(); }
  $('all').addEventListener('click', function () { setAll(true); });
  $('none').addEventListener('click', function () { setAll(false); });

  $('save').addEventListener('click', function (e) {
    var picked = cards.filter(function (c, i) { return boxes[i] && boxes[i].checked; });
    if (!cards.length || picked.length === cards.length) return;  // 전원이면 올려 둔 파일을 그대로 받는다
    e.preventDefault();
    if (!picked.length) return;
    var a = document.createElement('a');  // 일부만 고르면 그 사람들만 담은 파일을 바로 만든다
    a.href = URL.createObjectURL(new Blob([picked.join('')], { type: 'text/vcard' }));
    a.download = 'JTV7기.vcf';
    document.body.appendChild(a); a.click(); a.remove();
  });

  var me = (location.search.match(/[?&]me=(\\d+)/) || [])[1];
  var mine = me && document.querySelector('a.name[data-no="' + me + '"]');
  if (mine) show(mine);
})();
</script>
</body>
</html>
"""

names = "\n".join(f'    <a class="name" href="m/{no}.vcf" data-no="{no}">{html.escape(name)}</a>' for no, name, _ in rows)
page = PAGE.replace("@COUNT@", str(len(rows) - 1)).replace("@NAMES@", names)
(out / "index.html").write_text(page, encoding="utf-8", newline="\n")
print(f"OK {len(rows)}명 / 파일 {len(rows)}개 / 경로 /{slug}/")
