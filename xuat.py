"""Xuất bộ keyword final đã chia biến thể — cùng thứ tự với trang /kw-list (tab "Chọn cho sản phẩm").

Hai dạng, cùng một nguồn (`bang_final`):
  • Excel (.xlsx): sheet Tổng hợp, mỗi loại một sheet (Product · Function · Gift · Personalized · Occasion),
    Tất cả keyword, Ghi chú. Mỗi dòng là một keyword, kèm cột Mục / Nhóm / Biến thể / Mức sát… để lọc được.
  • Markdown: cho agent (Claude…) đọc thẳng bằng web fetch, không phải chạy JavaScript của trang.

L  = server.tom_tat_bo(meta, kem_dong=True)   (thông tin bộ + toàn bộ dòng đã gộp)
BT = server.tinh_bien_the(meta)                (kết quả chia biến thể, như /api/lists/<bộ>/bien-the)
"""

from __future__ import annotations

import time

import xlsx

SHEET = {"KW PRODUCT": "Product", "FUNCTION": "Function", "KW GIFTS": "Gift", "PERSONALIZED": "Personalized",
         "Seasonal": "Occasion"}
MUC = ["Nhóm 1", "Nhóm 2", "Nhóm 3", "Cần xem xét"]
MO_MUC = {"Nhóm 1": "biến thể có ở ≥ 3 ASIN", "Nhóm 2": "biến thể có ở 2 ASIN", "Nhóm 3": "biến thể có ở 1 ASIN",
          "Cần xem xét": "rank tốt nhất > 50", "Loại": "nhãn Không hợp (loại tay)",
          "Chưa vào biến thể": "keyword chưa khớp biến thể nào / dính negative"}
KY = {"2025-12": "12/2025", "current": "Kỳ hiện tại"}


def _nhom(n) -> str:
    return f"Nhóm {n}" if n else ""


def bang_final(L: dict, BT: dict) -> dict:
    """Danh sách khối theo đúng thứ tự trang web cho từng loại. Mỗi khối:
    {sheet, muc, nhom, ten, doi_tuong, so_asin, rank, sat, ten_sat, nhan, sv, kw:[...]}"""
    ten_sat = {int(k): v for k, v in (BT.get("ten_sat") or {}).items()}
    khoi = {sh: [] for sh in BT.get("thu_tu_sheet") or SHEET}

    def bien_the(v, muc):
        return {"sheet": v["sheet"], "muc": muc, "nhom": _nhom(v.get("nhom")), "ten": v["ten"],
                "doi_tuong": v.get("doi_tuong", False), "so_asin": v["so_asin"], "rank": v["rank"],
                "sat": v["sat"], "ten_sat": ten_sat.get(v["sat"], ""), "nhan": v.get("nhan") or "",
                "sv": sum(r["sv"] or 0 for r in v["kw"]), "kw": v["kw"]}

    for sh in khoi:
        chon = [v for v in BT.get("chon", []) if v["sheet"] == sh]
        for m in MUC:
            vs = [v for v in chon if v["muc"] == m]
            if m == "Cần xem xét":   # như trang web: trong Cần xem xét chia tiếp theo số ASIN (Nhóm 1 → 2 → 3)
                vs.sort(key=lambda v: (v.get("nhom") or 9))
            khoi[sh] += [bien_the(v, m) for v in vs]
        khoi[sh] += [bien_the(v, "Loại") for v in BT.get("loai", []) if v["sheet"] == sh]
        for p in (BT.get("phu") or {}).get(sh, []):
            khoi[sh].append({"sheet": sh, "muc": "Chưa vào biến thể", "nhom": "", "ten": p["ten"], "doi_tuong": False,
                             "so_asin": None, "rank": None, "sat": None, "ten_sat": "", "nhan": "",
                             "sv": sum(r["sv"] or 0 for r in p["kw"]), "kw": p["kw"]})
    root = {(sh, v["ten"]): (v.get("root"), v.get("bac")) for sh, ds in (BT.get("so_sanh") or {}).items() for v in ds}
    return {"NA": BT.get("NA") or 0, "asins": BT.get("asins") or [], "ky": BT.get("ky") or {}, "khoi": khoi,
            "root": root, "ten_sat": ten_sat}


def _thong_tin(L: dict, F: dict) -> list[tuple[str, str]]:
    s = L.get("stats") or {}
    return [("Bộ keyword", L.get("ten", "")), ("Mã", L.get("ma", "")), ("Link", L.get("link", "")),
            ("ASIN đối thủ", ", ".join(f"{a} ({KY.get(F['ky'].get(a), F['ky'].get(a) or '—')})" for a in F["asins"])),
            ("Đã quét", f"{L.get('so_xong', 0)}/{len(L.get('trang_thai_asin') or [])} ASIN"
                        + ("" if L.get("so_xong", 0) >= len(L.get("trang_thai_asin") or []) else " — CHƯA ĐỦ, kết quả còn thay đổi")),
            ("Keyword sau gộp", f"{s.get('gop', '')} (từ {s.get('goc', '')} dòng gốc, {s.get('trung', '')} dòng trùng)"),
            ("Xuất lúc", time.strftime("%Y-%m-%d %H:%M"))]


GIAI_THICH = [
    ("Loại (sheet)", "Personalized: có personalized/custom… → Product: có ornament → Function: có decor/decoration → "
                     "Gift: có gift → Occasion: có dịp lễ. Mỗi keyword chỉ thuộc 1 loại."),
    ("Mục", "Nhóm 1 / 2 / 3 = biến thể có ở ≥ 3 / 2 / 1 ASIN đối thủ. Cần xem xét = rank tốt nhất > 50. "
            "Loại = người dùng bấm Loại (không hợp sản phẩm). Chưa vào biến thể = keyword chưa khớp biến thể nào, "
            "khối 'Khác', hoặc dính negative."),
    ("Nhóm theo số ASIN", "Số ASIN có biến thể, kể cả khi đã vào Cần xem xét."),
    ("Mức sát", "Tự tính từ số ASIN dùng biến thể × rank tốt nhất: 5 Sát · 4 Khá sát · 3 Trung bình · 2 Xa · 1 Không hợp. "
                "≥3 ASIN: rank ≤20 → 5, 21–50 → 4, 51–75 → 2, 76–100 → 1. 2 ASIN: 4/3/2/1. 1 ASIN: 3/3/1/1."),
    ("Nhãn tay", "Nhãn người dùng gắn trên trang (Không hợp = đã loại)."),
    ("Thứ tự", "Trong mỗi mục: biến thể nhiều ASIN dùng chung trước, cùng số ASIN thì rank tốt nhất nhỏ hơn trước. "
               "Keyword trong biến thể xếp Search Volume giảm dần."),
    ("Ngoài bộ lọc", "Keyword có SV < 50 hoặc organic rank ngoài 1–100 không vào loại nào (chỉ có ở sheet Tất cả keyword)."),
]

COT_KW = [("Mục", 14), ("Nhóm theo số ASIN", 11), ("Biến thể", 26), ("Đối tượng", 9), ("Mức sát", 12), ("Điểm sát", 8),
          ("Nhãn tay", 10), ("ASIN dùng biến thể", 10), ("Rank tốt nhất biến thể", 11), ("Keyword", 46),
          ("Search Volume", 11), ("Trend %", 9), ("Organic Rank", 10), ("ASIN nguồn", 26), ("Số ASIN có kw", 10),
          ("Kỳ", 11), ("Lý do loại", 30)]
TO_MUC = {"Cần xem xét": "vang", "Loại": "xam"}


def _dong_kw(k: dict, r: dict, NA: int) -> list:
    return [k["muc"], k["nhom"], k["ten"], "x" if k["doi_tuong"] else "", k["ten_sat"], k["sat"], k["nhan"],
            f"{k['so_asin']}/{NA}" if k["so_asin"] is not None else "", k["rank"], r["keyword"], r["sv"], r["trend"],
            r["rank"], r["asin"], f"{r.get('so_asin', 1)}/{NA}", KY.get(r.get("ky"), r.get("ky") or ""),
            "; ".join(r.get("neg") or [])]


def xlsx_bytes(L: dict, BT: dict) -> bytes:
    F = bang_final(L, BT)
    NA, asins = F["NA"], F["asins"]
    wb = xlsx.Sach()

    # ---- Tổng hợp: mọi biến thể (như tab Tổng hợp trên web)
    th = wb.sheet("Tổng hợp", [("Loại", 12), ("Mục", 13), ("Nhóm theo số ASIN", 11), ("Biến thể", 28), ("Đối tượng", 9),
                               ("ASIN dùng", 9), ("Rank tốt nhất", 10)] + [(f"Rank {a}", 13) for a in asins] +
                  [("Tổng SV", 10), ("Số kw", 8), ("Mức sát", 12), ("Điểm sát", 8), ("Nhãn tay", 10), ("Bậc lọc", 11),
                   ("Root (kw rank tốt nhất)", 42)])
    per = {(v["sheet"], v["ten"]): v.get("per") or {} for v in BT.get("chon", []) + BT.get("loai", [])}
    for sh, ds in F["khoi"].items():
        for k in ds:
            if k["muc"] == "Chưa vào biến thể":
                continue
            root, bac = F["root"].get((sh, k["ten"]), (None, None))
            p = per.get((sh, k["ten"]), {})
            th.dong([SHEET[sh], k["muc"], k["nhom"], k["ten"], "x" if k["doi_tuong"] else "", f"{k['so_asin']}/{NA}", k["rank"]] +
                    [p.get(a) for a in asins] + [k["sv"], len(k["kw"]), k["ten_sat"], k["sat"], k["nhan"], bac or "", root or ""],
                    to=TO_MUC.get(k["muc"]))

    # ---- Mỗi loại một sheet, mỗi dòng một keyword
    vi_tri = {}
    for sh, ds in F["khoi"].items():
        ws = wb.sheet(SHEET[sh], COT_KW)
        xen = False
        for k in ds:
            xen = not xen
            to = TO_MUC.get(k["muc"]) or ("cam" if k["ten"] == "Loại bỏ (negative)" else
                                          "xam" if k["muc"] == "Chưa vào biến thể" else ("xanh" if xen else None))
            for r in k["kw"]:
                ws.dong(_dong_kw(k, r, NA), to=to)
                vi_tri.setdefault(r["keyword"].lower(), (sh, k))

    # ---- Tất cả keyword (cả ngoài bộ lọc), kèm loại / biến thể đã chia
    tc = wb.sheet("Tất cả keyword", [("Keyword", 46), ("Search Volume", 11), ("Trend %", 9), ("Organic Rank", 10),
                                     ("ASIN nguồn", 26), ("Số ASIN có kw", 10), ("Kỳ", 11), ("Loại", 12), ("Mục", 14),
                                     ("Biến thể", 26), ("Mức sát", 12)])
    for r in sorted(L.get("rows") or [], key=lambda r: -(r["sv"] or 0)):
        sh, k = vi_tri.get(r["keyword"].lower(), (None, None))
        tc.dong([r["keyword"], r["sv"], r["trend"], r["rank"], r["asin"], f"{r.get('so_asin', 1)}/{NA}",
                 KY.get(r.get("ky"), r.get("ky") or ""), SHEET.get(sh, "Ngoài bộ lọc"), k["muc"] if k else "",
                 k["ten"] if k else "", k["ten_sat"] if k else ""], to=None if k else "xam")

    gc = wb.sheet("Ghi chú", [("Mục", 22), ("Nội dung", 120)])
    for a, b in _thong_tin(L, F) + [("", "")] + GIAI_THICH:
        gc.dong([a, b])
    return wb.bytes()


def _o(v) -> str:
    return "—" if v is None or v == "" else (f"{v:,}" if isinstance(v, int) else str(v)).replace("|", "/")


def markdown(L: dict, BT: dict, *, kw: bool = True, loai: set | None = None, bo_phu: bool = False) -> str:
    """Bản chữ cho agent: thông tin bộ → bảng biến thể theo loại → keyword từng biến thể.
    kw=False: chỉ bảng biến thể. loai: chỉ các loại này ('product', 'gift'…). bo_phu: bỏ khối Chưa vào biến thể."""
    F = bang_final(L, BT)
    NA = F["NA"]
    out = [f"# {L.get('ten', '')}", ""]
    out += [f"- {a}: {b}" for a, b in _thong_tin(L, F)]
    out += ["", "Cột: Mục (Nhóm 1/2/3 = biến thể có ở ≥3/2/1 ASIN, Cần xem xét = rank tốt nhất > 50, Loại = bị loại tay), "
            "Mức sát 5 Sát · 4 Khá sát · 3 Trung bình · 2 Xa · 1 Không hợp. Keyword xếp theo Search Volume giảm dần.", ""]
    if BT.get("trong"):
        return "\n".join(out + ["_Bộ này chưa có dữ liệu keyword._", ""])
    for sh, ds in F["khoi"].items():
        if loai and SHEET[sh].lower() not in loai:
            continue
        ds = [k for k in ds if not (bo_phu and k["muc"] == "Chưa vào biến thể")]
        out += [f"## {SHEET[sh]}", ""]
        if not ds:
            out += ["_Không có keyword._", ""]
            continue
        out += ["| Mục | Nhóm | Biến thể | Mức sát | ASIN dùng | Rank tốt nhất | Tổng SV | Số kw |", "|---|---|---|---|---|---|---|---|"]
        for k in ds:
            ten = _o(k["ten"]) + (" (đối tượng)" if k["doi_tuong"] else "") + (" · nhãn " + k["nhan"] if k["nhan"] else "")
            sat = f"{k['sat']} {k['ten_sat']}" if k["ten_sat"] else "—"
            dung = f"{k['so_asin']}/{NA}" if k["so_asin"] is not None else "—"
            out.append(f"| {k['muc']} | {_o(k['nhom'])} | {ten} | {sat} | {dung} | {_o(k['rank'])} | {_o(k['sv'])} | {len(k['kw'])} |")
        out.append("")
        if not kw:
            continue
        for k in ds:
            out += [f"### {SHEET[sh]} · {k['muc']} · {k['ten']}", "", "| Keyword | SV | Rank | ASIN có |", "|---|---|---|---|"]
            out += [f"| {_o(r['keyword'])} | {_o(r['sv'])} | {_o(r['rank'])} | {r.get('so_asin', 1)}/{NA} |" for r in k["kw"]]
            out.append("")
    return "\n".join(out)
