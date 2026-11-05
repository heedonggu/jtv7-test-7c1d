"""중복 시험용 vcf(가짜 번호): 같은 이름·다른 번호 / 다른 이름·같은 번호. 각 2명이라 '모든 연락처 추가' 화면이 뜬다."""
import pathlib

site = pathlib.Path("site")


def card(name, tel):
    return "\r\n".join(["BEGIN:VCARD", "VERSION:3.0", f"N:;{name};;;", f"FN:{name}", "ORG:JTV 7기", f"TEL;TYPE=CELL:{tel}", "END:VCARD", ""])


(site / "t_samename.vcf").write_bytes((card("김하나", "010-9999-0001") + card("신규일", "010-9999-0002")).encode("utf-8"))
(site / "t_samenum.vcf").write_bytes((card("김하나B", "010-0000-1001") + card("신규이", "010-9999-0003")).encode("utf-8"))
print("extra vcf written:", sorted(p.name for p in site.glob("t_*.vcf")))
