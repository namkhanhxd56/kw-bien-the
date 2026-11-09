"""
Chia biến thể + phân loại keyword (bước 3) — khung PDF "Quy trình lọc KW ornament ra chia
nhom final" + lớp negative của bản kwfinal (bật/tắt, dòng dính negative tách khối, không xoá).

  1. Bộ lọc chuẩn: organic rank >= RANK_MIN và SV >= SV_MIN. Dòng ngoài bộ lọc để sheet riêng.
     Dòng kỳ hiện tại (ASIN không có keyword ở 12/2025, tức sản phẩm mới) được miễn lọc.
  2. Biến thể rút từ kw chứa "ornament", rank 1–50, bỏ "ornament" + từ phụ → phần còn lại.
     Người/AI chốt danh sách (config). Nhóm 1/2/3 = có ở N / N-1 / N-2 ASIN.
  3. Thứ tự lọc (waterfall): biến thể nhiều từ trước (3 từ → 2 từ), rồi 1 từ cụ thể, rồi 1 từ
     rộng; cùng bậc thì Nhóm 1 → 2 → 3; cùng nhóm thì rank tốt hơn trước.
  4. Tách: Product (có ornament) → Gift (có gift) → Function (từ công năng) → Seasonal (dịp lễ)
     → còn lại vào khối "chưa phân loại" của Function.
  5. Product/Gift chia khối theo biến thể (mỗi sheet một danh sách: root Product từ kw có ornament, root
     Gift từ kw có gift); Function chia theo từ công năng; Seasonal theo dịp lễ.
     Trong khối xếp organic rank tăng dần, hoà thì SV cao trước.
"""

from __future__ import annotations

import re

ROOT = "ornament"
SUF = ["", "s", "es", "'s", "er", "ers", "or", "ors", "ing", "ed", "al", "ist", "ian", "ish", "ese", "ic",
       "istic", "ly", "ness", "ful", "y", "ie", "ies", "sy", "my", "dy", "ma", "mer", "mers", "ming"]
TU_PHU = {"ornament", "ornaments", "christmas", "xmas", "tree", "for", "the", "a", "an", "of", "and",
          "with", "to", "on", "in", "decorations", "decoration", "holiday", "2025", "2026"}
FUNC_WORDS = ["tree topper", "light up", "snow globe", "decorations", "decoration", "decor", "hanging",
              "stuff", "merchandise", "merch", "figurine", "statue", "wreath", "magnet", "sign", "mug",
              "toy", "stocking", "nutcracker", "suncatcher"]
SEASON_WORDS = ["christmas", "xmas", "navidad", "santa", "holiday", "halloween", "easter", "thanksgiving",
                "valentine", "mother's day", "mothers day", "father's day", "fathers day", "new year",
                "st patrick"]


def toks(k: str) -> list[str]:
    return re.findall(r"[a-z0-9]+(?:'[a-z]+)?", k.lower().replace("+", " "))


def hit(w: str, T) -> bool:
    return any(t == w + s for t in T for s in SUF)


def grp_hit(g: str, T) -> bool:
    return all(hit(w, T) for w in g.split())


def excl_hit(e: str, k: str, T) -> bool:
    if e.startswith("="):
        w = e[1:]
        return (w in k) if " " in w else grp_hit(w, T)
    return e in k


def phrase_hit(p: str, k: str, T) -> bool:
    return bool(re.search(r"\b" + re.escape(p) + r"s?\b", k)) if " " in p else hit(p, T)


def find_neg(k: str, T, neg: dict, target_year: str) -> list[str]:
    out = []
    for cat, lst in neg.items():
        if cat.startswith("_"):
            continue
        for t in lst:
            if cat.startswith("Vat the khac (khi khong co ornament)") and hit(ROOT, T):
                continue
            if t.startswith("="):
                w = t[1:]
                ok = (" " in w and re.search(r"\b" + re.escape(w) + r"s?\b", k)) or \
                     (" " not in w and any(x in (w, w + "s", w + "es") for x in T))
            else:
                ok = t in k
            if ok:
                if t == "=stocking" and "stocking stuffer" in k:
                    continue
                out.append(f"{cat}: {t.lstrip('=')}")
    for y in re.findall(r"\b(20\d\d)\b", k):
        if y != target_year:
            out.append(f"Nam cu: {y}")
    return list(dict.fromkeys(out))


def goi_y_bien_the(rows: list[dict], rank_max: int = 50) -> list[dict]:
    """Bước 3.1 PDF: kw ornament rank 1–50, bỏ ornament + từ phụ, phần còn lại là ứng viên."""
    seen = {}
    for r in sorted([r for r in rows if r["rank"] and r["rank"] <= rank_max and hit(ROOT, toks(r["keyword"]))],
                    key=lambda r: (r["rank"], -(r["sv"] or 0))):
        rest = " ".join(t for t in toks(r["keyword"]) if t not in TU_PHU)
        if rest and rest not in seen:
            seen[rest] = {"ung_vien": rest, "rank": r["rank"], "vi_du": r["keyword"]}
    return list(seen.values())


def bac(v: dict) -> tuple:
    """Thứ tự waterfall: nhiều từ trước, rồi 1 từ cụ thể, rồi 1 từ rộng; trong bậc theo nhóm, rank."""
    n = len(v["name"].split())
    tier = 0 if n >= 2 else (2 if v.get("rong") else 1)
    return (tier, -n, v.get("nhom") or 9, v.get("rank") or 999)


def assign(k: str, T, order: list[dict]) -> str | None:
    for v in order:
        if any(grp_hit(g, T) for g in v["words"]) and not any(excl_hit(e, k, T) for e in v.get("exclude", [])):
            return v["name"]
    return None


def chay(rows: list[dict], asins: list[str], variants: list[dict], neg: dict, *,
         sv_min=50, rank_min=1, rank_root=50, target_year="2026", neg_on=True,
         mien_loc=("current",)) -> dict:
    """rows: dòng đã gộp (keyword, sv, trend, rank, asin, cac_asin, ky). variants: config đã chốt.
    mien_loc: kỳ dữ liệu không áp bộ lọc SV/rank (kỳ hiện tại = sản phẩm mới)."""
    NA = len(asins)
    for r in rows:
        r["T"] = toks(r["keyword"])
        r["k"] = " ".join(r["T"])
        r["trong_loc"] = r.get("ky") in mien_loc or (
            r["rank"] is not None and r["rank"] >= rank_min and (r["sv"] or 0) >= sv_min)
        r["neg"] = find_neg(r["k"], r["T"], neg, target_year) if neg_on else []

    # Danh sách biến thể riêng cho từng sheet (PDF: Gift có danh sách biến thể riêng). Root của biến thể
    # Product lấy từ kw có "ornament", của Gift lấy từ kw có "gift" mà không có "ornament".
    la_product = lambda r: hit(ROOT, r["T"])
    la_gift = lambda r: not hit(ROOT, r["T"]) and hit("gift", r["T"])
    order, bo = _xep(rows, asins, variants, la_product, rank_root)
    order_gift, bo_gift = _xep(rows, asins, variants, la_gift, rank_root)
    for v in order_gift:
        v["root_tu"] = "Gift"
    # Biến thể không có root ở kw quà nhưng có root bên Product: vẫn dùng cho Gift, mượn thứ hạng Product
    co = {v["name"] for v in order_gift}
    order_gift = sorted(order_gift + [{**v, "root_tu": "Product"} for v in order if v["name"] not in co], key=bac)
    bo_gift = [n for n in bo_gift if n not in {v["name"] for v in order_gift}]
    for v in order:
        v["root_tu"] = "Product"
    for r in rows:
        r["var"] = assign(r["k"], r["T"], order_gift if la_gift(r) else order)

    # tách sheet
    for r in rows:
        T, k = r["T"], r["k"]
        if not r["trong_loc"]:
            r["sheet"], r["khoi"] = "Ngoai bo loc", "Ngoài bộ lọc"
        elif hit(ROOT, T):
            r["sheet"], r["khoi"] = "KW PRODUCT", r["var"] or "chưa phân loại"
        elif hit("gift", T):
            r["sheet"], r["khoi"] = "KW GIFTS", r["var"] or "chưa phân loại"
        else:
            fw = next((w for w in FUNC_WORDS if phrase_hit(w, k, T)), None)
            sw = next((w for w in SEASON_WORDS if phrase_hit(w, k, T)), None)
            if fw:
                r["sheet"], r["khoi"] = "FUNCTION", fw
            elif sw:
                r["sheet"], r["khoi"] = "Seasonal", sw
            else:
                r["sheet"], r["khoi"] = "FUNCTION", "chưa phân loại"
        if r["neg"] and r["trong_loc"]:
            r["khoi"] = "Loại bỏ (negative)"
    return {"order": order, "bo": bo, "order_gift": order_gift, "bo_gift": bo_gift,
            "rows": rows, "NA": NA, "asins": asins}


def _xep(rows: list[dict], asins: list[str], variants: list[dict], la_goc, rank_root: int):
    """Xếp thứ tự lọc cho một sheet: rank tốt nhất của biến thể trong từng ASIN, chỉ tính kw gốc của sheet
    (la_goc), trong bộ lọc, rank 1–rank_root, không negative. Biến thể không có root ở ASIN nào bị bỏ."""
    NA = len(asins)
    vs = [dict(v) for v in variants]
    order = sorted(vs, key=bac)
    for _ in range(5):
        gan = {id(r): assign(r["k"], r["T"], order) for r in rows}
        for v in order:
            per = {}
            for a in asins:
                c = [r for r in rows if gan[id(r)] == v["name"] and a in r.get("cac_asin", [r["asin"]])
                     and r["trong_loc"] and r["rank"] is not None and r["rank"] <= rank_root
                     and la_goc(r) and not r["neg"]]
                c.sort(key=lambda r: (r["rank"], -(r["sv"] or 0)))
                per[a] = {"rank": c[0]["rank"], "root": c[0]["keyword"]} if c else None
            v["per"] = per
            cnt = sum(1 for a in asins if per[a])
            v["so_asin"] = cnt
            v["nhom"] = (NA - cnt + 1) if cnt else None
            best = [p for p in per.values() if p]
            v["rank"] = min(p["rank"] for p in best) if best else None
            v["root"] = min(best, key=lambda p: p["rank"])["root"] if best else None
        new = sorted(vs, key=bac)
        if [v["name"] for v in new] == [v["name"] for v in order]:
            break
        order = new
    return [v for v in order if v["nhom"]], [v["name"] for v in order if not v["nhom"]]


def xuat_xlsx(res: dict, path: str, ten: str, tom_tat: list[list]) -> dict:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    F_T = PatternFill("solid", fgColor="FF2F5597")
    F_K = PatternFill("solid", fgColor="FFC55A11")
    F_X = PatternFill("solid", fgColor="FF7F7F7F")
    WHITE = Font(bold=True, color="FFFFFFFF")
    COLS = ["Keyword Phrase", "Search Volume", "Search Volume Trend", "Organic Rank", "ASIN nguồn",
            "Biến thể khớp", "Lý do loại"]
    order, rows, NA = res["order"], res["rows"], res["NA"]
    order_gift = res.get("order_gift", order)
    nhom = {"KW PRODUCT": {v["name"]: v["nhom"] for v in order}, "KW GIFTS": {v["name"]: v["nhom"] for v in order_gift}}
    written = {}

    wb = Workbook()
    wb.remove(wb.active)

    def banner(ws, text, fill):
        ws.append([text])
        r = ws.max_row
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=len(COLS))
        ws.cell(r, 1).fill = fill
        ws.cell(r, 1).font = WHITE

    def put(ws, rs):
        for r in sorted(rs, key=lambda r: (r["rank"] if r["rank"] is not None else 9e9, -(r["sv"] or 0))):
            ws.append([r["keyword"], r["sv"], r["trend"], r["rank"], r["asin"], r["var"] or "",
                       "; ".join(r["neg"])])
            written[r["k"]] = written.get(r["k"], 0) + 1

    def head(ws, widths=(46, 14, 12, 12, 14, 22, 50)):
        ws.append(COLS)
        for c in ws[1]:
            c.font = Font(bold=True)
        for i, w in enumerate(widths):
            ws.column_dimensions[chr(65 + i)].width = w
        ws.freeze_panes = "A2"

    def vol(rs):
        return f"{len(rs)} kw . {sum(r['sv'] or 0 for r in rs):,}".replace(",", ".") + " volume"

    t = wb.create_sheet("Tom tat")
    for line in [[ten], []] + tom_tat:
        t.append(line)
    t["A1"].font = Font(bold=True, size=13)
    t.column_dimensions["A"].width = 26
    t.column_dimensions["B"].width = 120

    wv = wb.create_sheet("BIEN THE")
    for tieu_de, ds, bo in [("KW PRODUCT (root = kw có ornament)", order, res["bo"]),
                            ("KW GIFTS (root = kw có gift, không có ornament; không có thì mượn Product)", order_gift, res.get("bo_gift", []))]:
        if wv.max_row > 1:
            wv.append([])
        wv.append([tieu_de])
        wv.cell(wv.max_row, 1).font = Font(bold=True, size=12)
        wv.append(["Thứ tự lọc", "Biến thể", "Bậc", "Nhóm", "Số ASIN có", "Rank tốt nhất", "Root", "Root từ"] +
                  [f"Rank {a}" for a in res["asins"]] + ["Từ khớp", "Loại trừ"])
        for c in wv[wv.max_row]:
            c.font = Font(bold=True)
        for i, v in enumerate(ds, 1):
            b = bac(v)[0]
            wv.append([i, v["name"], ["nhiều từ", "1 từ cụ thể", "1 từ rộng"][b], f"Nhóm {v['nhom']}",
                       f"{v['so_asin']}/{NA}", v["rank"], v["root"], v.get("root_tu", "")] +
                      [(v["per"][a] or {}).get("rank") for a in res["asins"]] +
                      [" ; ".join(v["words"]), ", ".join(v.get("exclude", []))])
        if bo:
            wv.append(["", "Không có root rank 1–50 (bị bỏ):", ", ".join(bo)])
    for col, w in zip("ABCDEFG", [10, 22, 12, 9, 11, 13, 40]):
        wv.column_dimensions[col].width = w

    for sheet in ["KW PRODUCT", "KW GIFTS", "FUNCTION", "Seasonal"]:
        ws = wb.create_sheet(sheet)
        head(ws)
        rs = [r for r in rows if r["sheet"] == sheet]
        if sheet in ("KW PRODUCT", "KW GIFTS"):
            keys = [v["name"] for v in (order if sheet == "KW PRODUCT" else order_gift)]
            for kname in keys:
                b = [r for r in rs if r["khoi"] == kname]
                if b:
                    banner(ws, f"{kname} — Nhóm {nhom[sheet][kname]} — {vol(b)}", F_T)
                    put(ws, b)
        else:
            words = FUNC_WORDS if sheet == "FUNCTION" else SEASON_WORDS
            for w in words:
                b = [r for r in rs if r["khoi"] == w]
                if b:
                    banner(ws, f"{w} — {'Function' if sheet == 'FUNCTION' else 'Seasonal'} — {vol(b)}", F_T)
                    put(ws, b)
        b = [r for r in rs if r["khoi"] == "chưa phân loại"]
        if b:
            banner(ws, f"chưa phân loại — Nhóm chưa phân loại — {vol(b)}", F_X)
            put(ws, b)
        b = [r for r in rs if r["khoi"] == "Loại bỏ (negative)"]
        if b:
            banner(ws, f"Loại bỏ (negative) — {vol(b)}", F_K)
            put(ws, b)

    ws = wb.create_sheet("Ngoai bo loc")
    head(ws)
    put(ws, [r for r in rows if r["sheet"] == "Ngoai bo loc"])

    for ws in wb.worksheets:
        for row in ws.iter_rows(min_row=2):
            for c in row:
                c.alignment = Alignment(vertical="top")
    wb.save(path)
    tong = len({r["k"] for r in rows})
    return {"tong": tong, "ghi": sum(written.values()), "trung": sum(1 for v in written.values() if v > 1),
            "thieu": tong - len(written)}
