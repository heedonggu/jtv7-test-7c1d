"""중복 시험용 vcf(가짜 번호). 각 2명이라 '모든 연락처 추가' 화면(여러 명 가져오기 화면)이 뜬다.
g1 = Save 묶음, g2 = Add All 묶음, g2n = g2와 같은 이름·다른 번호(+새 사람), g2p = g2와 같은 번호·다른 이름(+새 사람)."""
import pathlib

site = pathlib.Path("site")


def card(name, tel):
    return "\r\n".join(["BEGIN:VCARD", "VERSION:3.0", f"N:;{name};;;", f"FN:{name}", "ORG:JTV 7기", f"TEL;TYPE=CELL:{tel}", "END:VCARD", ""])


FILES = {
    "g1.vcf": [("가나다", "010-1111-0001"), ("라마바", "010-1111-0002")],
    "g2.vcf": [("사아자", "010-2222-0001"), ("차카타", "010-2222-0002")],
    "g2n.vcf": [("사아자", "010-2222-9001"), ("신규삼", "010-2222-0003")],
    "g2p.vcf": [("사아자B", "010-2222-0001"), ("신규사", "010-2222-0004")],
}
for fn, people in FILES.items():
    (site / fn).write_bytes("".join(card(n, t) for n, t in people).encode("utf-8"))
print("extra vcf written:", sorted(FILES))
