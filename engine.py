"""
Chia biến thể + phân loại keyword (bước 3) — khung PDF "Quy trình lọc KW ornament ra chia
nhom final" + lớp negative của bản kwfinal (bật/tắt, dòng dính negative tách khối, không xoá).

  1. Bộ lọc chuẩn: organic rank trong [RANK_MIN, RANK_MAX] và SV >= SV_MIN. Dòng ngoài bộ lọc để sheet riêng.
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


# ============================================================ chia nhóm theo dữ liệu (đúng PDF bước 3–5)
# 3.1 Biến thể rút từ chính dữ liệu: kw (đọc theo rank tăng dần), bỏ từ gốc của sheet ("ornament" hoặc "gift")
#     và các chữ chung chung, phần còn lại là biến thể; mỗi biến thể lấy 1 lần.
# 3.2 Mỗi ASIN: biến thể có trong top 1–50 kw gốc của ASIN đó (rank tốt nhất). Số ASIN có càng nhiều xếp
#     càng cao: có ở cả N ASIN = Nhóm 1, N-1 = Nhóm 2, ...
# 5   Mỗi kw chỉ vào 1 biến thể, lọc theo bậc: nhiều từ (3 → 2) → 1 từ cụ thể → 1 từ rộng; cùng bậc Nhóm 1 → 3,
#     rồi rank. So với sản phẩm (sát / xa / không hợp) là bước SAU, chỉ gắn nhãn, không bỏ biến thể.
CHUNG = {"christmas", "xmas", "tree", "for", "the", "a", "an", "of", "and", "with", "to", "on", "in", "my", "your",
         "decorations", "decoration", "holiday", "gift", "gifts", "idea", "ideas", "present", "presents",
         "women", "woman", "men", "man", "her", "him", "adult", "adults", "is", "as", "at", "from", "by"}
# Từ cá nhân hoá: kw có một trong các từ này vào riêng mục Personalized (đặt sau Gift), không còn là negative
PERSONAL = {"personalized", "personalize", "personalised", "personalise", "personalization", "personalisation",
            "custom", "customized", "customised", "customize", "customise", "customizable"}
# Function của ornament luôn là decor / decoration(s): kw không có ornament mà có các từ này vào Function, chia biến thể như Product
DECOR = {"decor", "decors", "decoration", "decorations", "decorative", "decorating", "decorate"}
# Gift chia theo đối tượng: kw gift có các từ này thì biến thể là đối tượng (xét trước biến thể chủ đề)
DOI_TUONG = {"women", "woman", "womens", "men", "man", "mens", "her", "him", "his", "she", "he", "guy", "guys", "lady", "ladies",
             "mom", "mother", "mum", "mama", "dad", "father", "papa", "grandma", "grandmother", "grandpa", "grandfather",
             "nana", "grandparent", "grandparents", "parent", "parents", "wife", "husband", "boyfriend", "girlfriend",
             "fiance", "fiancee", "couple", "couples", "daughter", "son", "sister", "brother", "sibling", "aunt", "uncle",
             "niece", "nephew", "granddaughter", "grandson", "grandkid", "grandkids", "kid", "kids", "child", "children",
             "boy", "boys", "girl", "girls", "teen", "teens", "teenager", "teenagers", "toddler", "baby", "adult", "adults",
             "friend", "friends", "bestie", "bff", "coworker", "coworkers", "boss", "employee", "employees", "teacher",
             "teachers", "nurse", "nurses", "family", "everyone"}
DAU_DOI_TUONG = {"lover", "lovers", "owner", "owners", "fan", "fans", "rider", "riders", "enthusiast", "enthusiasts",
                 "mom", "dad", "girl", "boy"}   # "horse lover", "horse girl": giữ cả chữ đứng trước
GOC = {"KW PRODUCT": ("ornament",), "FUNCTION": tuple(sorted(DECOR)), "KW GIFTS": ("gift",),
       "PERSONALIZED": ("ornament", "gift", *sorted(PERSONAL))}
PHU = ("chưa phân loại", "Khác", "Loại bỏ (negative)")   # khối phụ: chưa vào biến thể / không thuộc loại nào / negative
RANK_XEM_XET = 50   # biến thể có rank tốt nhất > mức này vào mục "Cần xem xét"
RONG = {"funny", "fun", "cute", "new", "first", "unique", "cool", "best", "beautiful",
        "pretty", "small", "large", "big", "mini", "vintage", "cheap"}


def _chuan_tok(T: list[str], vocab: set[str]) -> list[str]:
    out = []
    for t in T:
        if len(t) > 3 and t.endswith("s") and not t.endswith("ss") and t[:-1] in vocab:
            t = t[:-1]
        out.append(t)
    return out


def _co(w: str, T) -> bool:
    """Khớp nguyên từ; từ ngắn (us, uk…) chỉ khớp chính nó hoặc số nhiều, tránh 'us' khớp 'used'."""
    return (w in T or w + "s" in T) if len(w) <= 3 else hit(w, T)


def _thuoc(v: str, T) -> bool:
    return all(_co(w, T) for w in v.split())


def _bac2(v: dict) -> tuple:
    n = len(v["ten"].split())
    tier = -1 if v.get("doi_tuong") else (0 if n >= 2 else (2 if v["ten"] in RONG else 1))   # đối tượng (Gift) lọc trước
    return (tier, -n, v["nhom"], v["rank"], -v["sv_root"])


THU_TU_SHEET = ["KW PRODUCT", "FUNCTION", "KW GIFTS", "PERSONALIZED", "Seasonal"]   # Product → Function → Gift → Personalized → Occasion
TU_KHOI = {"Seasonal": SEASON_WORDS}


def phan_sheet(T: list[str], k: str) -> tuple[str, str | None]:
    """Thứ tự phân loại: có từ cá nhân hoá (personalized, custom…) → Personalized; không thì có ornament → Product;
    không thì có decor / decoration(s) → Function (kể cả có gift); không thì có gift → Gift; không thì có dịp lễ →
    Occasion (Seasonal); còn lại → khối 'Khác' của Function. Trả (sheet, từ khối) — từ khối chỉ có ở Occasion / 'Khác'."""
    if any(t in PERSONAL for t in T):
        return "PERSONALIZED", None
    if hit("ornament", T):
        return "KW PRODUCT", None
    if any(t in DECOR for t in T):
        return "FUNCTION", None
    if hit("gift", T):
        return "KW GIFTS", None
    sw = next((w for w in SEASON_WORDS if phrase_hit(w, k, T)), None)
    if sw:
        return "Seasonal", sw
    return "FUNCTION", "Khác"


def _nhom(so_asin: int) -> int | None:
    """Nhóm theo số ASIN dùng biến thể: ≥ 3 ASIN → Nhóm 1, 2 ASIN → Nhóm 2, 1 ASIN → Nhóm 3."""
    return 1 if so_asin >= 3 else (2 if so_asin == 2 else (3 if so_asin == 1 else None))


def _muc(v: dict, xem_xet: int = RANK_XEM_XET) -> str:
    """Mục hiển thị: 'Nhóm 1/2/3', hoặc 'Cần xem xét' khi rank tốt nhất > xem_xet (hay không ASIN nào có rank)."""
    if v["rank"] is None or v["rank"] > xem_xet or not v.get("nhom"):
        return "Cần xem xét"
    return f"Nhóm {v['nhom']}"


# Mức sát với sản phẩm (5 = sát nhất … 1 = không hợp), tự tính theo ma trận số ASIN dùng biến thể × rank tốt nhất.
# Rank 51–100 kéo mức xuống dần; 1 ASIN mà rank vẫn ở page 1 (≤ 50) là mức trung bình (3).
#            rank:  ≤20  21–50  51–75  76–100
MA_TRAN_SAT = {3: (5, 4, 2, 1),     # ≥ 3 ASIN
               2: (4, 3, 2, 1),
               1: (3, 3, 1, 1)}
TEN_SAT = {5: "Sát", 4: "Khá sát", 3: "Trung bình", 2: "Xa", 1: "Không hợp"}


def muc_sat(so_asin: int, rank: int | None) -> int:
    if not so_asin or rank is None or rank > 100:
        return 1
    cot = 0 if rank <= 20 else 1 if rank <= 50 else 2 if rank <= 75 else 3
    return MA_TRAN_SAT[min(so_asin, 3)][cot]


def _rut_bien_the(ds: list, goc: tuple, rank_root: int, doi_tuong: bool = False) -> dict:
    """3.1: kw gốc của sheet (rank 1–rank_root, không negative), bỏ từ gốc + chữ chung, phần còn lại là biến thể.
    doi_tuong (Gift): kw có từ chỉ người nhận thì biến thể là phần đối tượng ("women", "horse lover"), không phải chủ đề.
    ds: [(asin, rank, sv, keyword, N)] đã lọc đúng sheet. Trả {tên: {per: {asin: rank tốt nhất}, …}}."""
    bt = {}
    chung = CHUNG - DOI_TUONG if doi_tuong else CHUNG
    for a, rank, sv, kw, N in sorted(ds, key=lambda x: (x[1], -x[2])):
        con = [t for t in N if t not in chung and t not in PERSONAL and not any(hit(g, [t]) for g in goc)
               and not re.fullmatch(r"20\d\d", t)]
        dt = False
        if doi_tuong and any(t in DOI_TUONG or t in DAU_DOI_TUONG for t in con):
            con = [t for i, t in enumerate(con) if t in DOI_TUONG or t in DAU_DOI_TUONG
                   or (i + 1 < len(con) and con[i + 1] in DAU_DOI_TUONG)]
            dt = True
        if not con:
            continue
        ten = " ".join(dict.fromkeys(con))
        v = bt.setdefault(ten, {"ten": ten, "per": {}, "vi_du": kw, "sv_root": sv, "doi_tuong": dt})
        v["per"].setdefault(a, {"rank": rank, "kw": kw})
    return bt


def _gom(rs: list, thu_tu: list) -> None:
    """5: mỗi kw vào biến thể đầu tiên khớp theo thứ tự lọc; dính negative thì vào khối negative."""
    for r in rs:
        v = None if r["neg"] or r.get("tu") == "Khác" else next((v for v in thu_tu if _thuoc(v["ten"], r["N"])), None)
        r["var"] = v["ten"] if v else None
        r["khoi"] = "Loại bỏ (negative)" if r["neg"] else (r["var"] or ("Khác" if r.get("tu") == "Khác" else "chưa phân loại"))


def chia_nhom(rows: list[dict], asins: list[str], neg: dict, *, theo_asin: dict | None = None, sv_min=50, rank_min=1,
              rank_max=100, rank_root=100, xem_xet=RANK_XEM_XET, target_year="2026", mien_loc=("current",)) -> dict:
    """rows: kw đã gộp (để chia khối). theo_asin: {asin: {"rows": [...], "period_used": ...}} dữ liệu Cerebro riêng
    từng ASIN, dùng cho bước 3.2 (rank tốt nhất của biến thể TRONG từng ASIN); thiếu thì suy từ dòng gộp.
    Sheet theo thứ tự Product → Function → Gift → Personalized → Occasion. Product / Gift / Personalized: biến thể
    rút từ dữ liệu (kw của sheet rank 1–rank_root). Function / Occasion: khối theo từ công năng / dịp lễ, số ASIN =
    số ASIN có kw của khối (mọi rank), rank tốt nhất = rank tốt nhất của kw khối trong từng ASIN.
    Nhóm theo số ASIN dùng (≥3 → 1, 2 → 2, 1 → 3); rank tốt nhất > xem_xet thì vào mục 'Cần xem xét'."""
    NA = len(asins)
    # từ cá nhân hoá giờ là một mục riêng, không còn là negative (cấu hình cũ vẫn ghi =personalized, =custom)
    neg = {c: [t for t in l if t.lstrip("=") not in PERSONAL] if isinstance(l, list) else l for c, l in neg.items()}
    tach = lambda kw: toks(kw.replace("u.s.", "us").replace("u.s", "us"))
    vocab = set()
    for r in rows:
        r["T"] = tach(r["keyword"])
        vocab.update(r["T"])

    def chuan(x: dict, a=None, ky=None) -> dict:
        T = tach(x["keyword"])
        d = {**x, "T": T, "k": " ".join(T), "N": _chuan_tok(T, vocab)}
        if a is not None:
            d.update(asin=a, ky=ky)
        ky = d.get("ky")
        d["trong_loc"] = ky in mien_loc or (d["rank"] is not None and rank_min <= d["rank"] <= rank_max
                                            and (d["sv"] or 0) >= sv_min)
        d["neg"] = find_neg(d["k"], T, neg, target_year)
        d["sheet"], d["tu"] = ("Ngoai bo loc", None) if not d["trong_loc"] else phan_sheet(T, d["k"])
        return d

    rows[:] = [chuan(r) for r in rows]
    so_asin_kw = {r["keyword"]: r.get("so_asin", 1) for r in rows}
    rieng = {}   # dòng của từng ASIN (đã phân sheet), cho bước 3.2 và tầng 1
    for a in asins:
        if theo_asin and a in theo_asin:
            ky = theo_asin[a].get("period_used")
            rieng[a] = [{**chuan(x, a, ky), "so_asin": so_asin_kw.get(x["keyword"], 1)} for x in theo_asin[a]["rows"]]
        else:
            rieng[a] = [r for r in rows if a in (r.get("cac_asin") or [r["asin"]])]

    def khoi_tu(sheet: str, ds_theo_asin: dict) -> list:
        """Function / Occasion: một khối cho mỗi từ công năng / dịp lễ có kw."""
        out = []
        for w in TU_KHOI[sheet]:
            per = {}
            for a, ds in ds_theo_asin.items():
                c = [d for d in ds if d["sheet"] == sheet and d["tu"] == w and not d["neg"] and d["rank"] is not None]
                if c:
                    m = min(c, key=lambda d: (d["rank"], -(d["sv"] or 0)))
                    per[a] = {"rank": m["rank"], "kw": m["keyword"]}
            out.append({"ten": w, "per": per, "so_asin": len(per), "nhom": _nhom(len(per)),
                        "rank": min((p["rank"] for p in per.values()), default=None), "vi_du": None, "sv_root": 0, "tu": True})
        return out

    ket = {}
    for sheet in THU_TU_SHEET:
        rs = [r for r in rows if r["sheet"] == sheet]
        if sheet in GOC:
            nguon = [(a, d["rank"], d["sv"] or 0, d["keyword"], d["N"]) for a in asins for d in rieng[a]
                     if d["sheet"] == sheet and d["rank"] is not None and d["rank"] <= rank_root and not d["neg"]
                     and d["tu"] != "Khác"]
            bt = _rut_bien_the(nguon, GOC[sheet], rank_root, doi_tuong=sheet == "KW GIFTS")
            for v in bt.values():
                v["per"] = {a: v["per"].get(a) for a in asins}
                co = [p for p in v["per"].values() if p]
                v["so_asin"], v["nhom"], v["rank"] = len(co), _nhom(len(co)), min(p["rank"] for p in co)
            thu_tu = sorted(bt.values(), key=_bac2)
            _gom(rs, thu_tu)
        else:
            for r in rs:
                r["var"] = r["tu"] if r["tu"] != "chưa phân loại" else None
                r["khoi"] = "Loại bỏ (negative)" if r["neg"] else r["tu"]
            thu_tu = khoi_tu(sheet, rieng)
            for v in thu_tu:
                v["per"] = {a: v["per"].get(a) for a in asins}
        for v in thu_tu:
            b = [r for r in rs if r["khoi"] == v["ten"]]
            v["so_kw"], v["sv"] = len(b), sum(r["sv"] or 0 for r in b)
        for v in thu_tu:
            v["muc"], v["sat"] = _muc(v, xem_xet), muc_sat(v["so_asin"], v["rank"])
        ket[sheet] = [v for v in thu_tu if v["so_kw"] or sheet in GOC]
    for r in rows:
        if r["sheet"] == "Ngoai bo loc":
            r["khoi"], r["var"] = "Ngoài bộ lọc", None

    # Tầng 1: từng ASIN đối thủ có biến thể nào (rank tốt nhất trong chính ASIN đó), rồi gom kw CỦA ASIN ĐÓ
    # vào các biến thể của nó theo cùng rule lọc.
    tung = {}
    for a in (asins if theo_asin else []):
        ds = rieng[a]
        cua = {}
        for sheet in THU_TU_SHEET:
            rs = [d for d in ds if d["sheet"] == sheet]
            if sheet in GOC:
                nguon = [(a, d["rank"], d["sv"] or 0, d["keyword"], d["N"]) for d in rs
                         if d["rank"] is not None and d["rank"] <= rank_root and not d["neg"] and d["tu"] != "Khác"]
                order = []
                for v in _rut_bien_the(nguon, GOC[sheet], rank_root, doi_tuong=sheet == "KW GIFTS").values():
                    p0 = v["per"][a]
                    order.append({"ten": v["ten"], "rank": p0["rank"], "root": p0["kw"], "nhom": 1, "sv_root": v["sv_root"],
                                  "doi_tuong": v["doi_tuong"]})
                order.sort(key=_bac2)
                _gom(rs, order)
            else:
                for d in rs:
                    d["khoi"] = "Loại bỏ (negative)" if d["neg"] else d["tu"]
                order = [{"ten": v["ten"], "rank": (v["per"].get(a) or {}).get("rank"), "root": (v["per"].get(a) or {}).get("kw"),
                          "nhom": 1, "sv_root": 0, "tu": True} for v in khoi_tu(sheet, {a: ds})]
            for v in order:
                b = [d for d in rs if d["khoi"] == v["ten"]]
                v["so_kw"], v["sv"] = len(b), sum(d["sv"] or 0 for d in b)
            cua[sheet] = [v for v in order if v["so_kw"]] if sheet not in GOC else order
        tung[a] = {"ky": theo_asin[a].get("period_used"), "rows": ds, "bien_the": cua}
    return {"bien_the": ket, "rows": rows, "NA": NA, "asins": asins, "tung_asin": tung}


THU_TU_MUC = {"Nhóm 1": 1, "Nhóm 2": 2, "Nhóm 3": 3, "Cần xem xét": 4}


def _rk(v: dict) -> float:
    return v["rank"] if v["rank"] is not None else 9e9


def xep_uu_tien(ket: dict, danh_gia: dict, loai: set) -> tuple[list, list]:
    """Tầng 3: biến thể cho sản phẩm của mình. Product → Function → Gift → Personalized → Occasion (như thứ tự chia
    sheet); trong mỗi loại: Nhóm 1 → 2 → 3 → Cần xem xét; trong mục, nhiều ASIN đối thủ dùng chung trước, cùng số
    ASIN thì rank tốt nhất nhỏ hơn trước. Biến thể có nhãn trong `loai` bị loại ra riêng."""
    chon, bo = [], []
    for sheet, ds in ket.items():
        for v in ds:
            if not v["so_kw"]:
                continue
            x = {**v, "sheet": sheet, "nhan": danh_gia.get(v["ten"], "")}
            (bo if x["nhan"] in loai else chon).append(x)
    thu_tu_sheet = {s: i for i, s in enumerate(THU_TU_SHEET)}
    chon.sort(key=lambda v: (thu_tu_sheet[v["sheet"]], THU_TU_MUC[v["muc"]], -v["so_asin"], _rk(v), -v["sv"]))
    bo.sort(key=lambda v: (thu_tu_sheet[v["sheet"]], -v["so_asin"], _rk(v)))
    return chon, bo


TEN_SHEET = {"KW PRODUCT": "Product", "FUNCTION": "Function", "KW GIFTS": "Gift", "PERSONALIZED": "Personalized",
             "Seasonal": "Occasion"}


def _bac_ten(v: dict, sheet: str) -> str:
    if sheet == "Seasonal":
        return "dịp lễ"
    if v.get("doi_tuong"):
        return "đối tượng"
    return ["nhiều từ", "1 từ cụ thể", "1 từ rộng"][_bac2(v)[0]]


def _root(v: dict) -> str | None:
    co = [p for p in v["per"].values() if p]
    return min(co, key=lambda p: p["rank"])["kw"] if co else None


def xuat_nhom_xlsx(res: dict, path: str, ten: str, tom_tat: list[list], danh_gia: dict | None = None,
                   loai: set | None = None) -> dict:
    """Sheet theo 3 tầng: '1. <ASIN>' (biến thể + kw của từng ASIN đối thủ), '2. So sanh ASIN' (biến thể dùng
    chung, rank tốt nhất ở từng ASIN), '3. Chon cho SP' (biến thể đúng sản phẩm, gần → xa, loại không sát);
    sau đó là bảng chia đủ (KW PRODUCT / KW GIFTS / FUNCTION / Seasonal / Ngoai bo loc) để kiểm mỗi kw đúng 1 lần.
    Mỗi khối: dòng biến thể in đậm đứng đầu (tổng SV, rank tốt nhất, số ASIN, số kw), kw gom bên dưới."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    danh_gia, loai = danh_gia or {}, loai or set()
    NA, asins, rows = res["NA"], res["asins"], res["rows"]
    COLS = ["Keyword Phrase", "Search Volume", "Search Volume Trend", "Organic Rank", "ASIN nguồn",
            "Số ASIN có kw", "Kỳ dữ liệu", "Lý do loại"]
    F_V = PatternFill("solid", fgColor="FFDCE6F1")
    F_X = PatternFill("solid", fgColor="FFEDEDED")
    F_K = PatternFill("solid", fgColor="FFFBE4D5")
    F_H = PatternFill("solid", fgColor="FF1F3864")
    B = Font(bold=True)
    KY = {"2025-12": "12/2025", "current": "hiện tại"}
    written = {}
    wb = Workbook()
    wb.remove(wb.active)

    def dau(ws, cols=COLS, widths=(48, 14, 12, 12, 30, 12, 11, 44)):
        ws.append(cols)
        for c in ws[1]:
            c.font = B
        for col, w in zip("ABCDEFGHIJKL", widths):
            ws.column_dimensions[col].width = w
        ws.freeze_panes = "A2"
        ws.sheet_properties.outlinePr.summaryBelow = False   # dòng biến thể nằm TRÊN nhóm, như mẫu

    def muc(ws, text):
        ws.append([text])
        ws.cell(ws.max_row, 1).font = Font(bold=True, color="FFFFFFFF")
        for c in ws[ws.max_row]:
            c.fill = F_H

    def khoi(ws, tieu_de, rs, ghi_chu, fill, rank=None, dem=False):
        ws.append([tieu_de, sum(r["sv"] or 0 for r in rs), None, rank, ghi_chu, f"{len(rs)} kw", None, None])
        for c in ws[ws.max_row]:
            c.font = B
            c.fill = fill
        for r in sorted(rs, key=lambda r: (-(r["sv"] or 0), r["rank"] if r["rank"] is not None else 9e9)):   # SV cao trước
            ws.append([r["keyword"], r["sv"], r["trend"], r["rank"], r["asin"],
                       f"{r.get('so_asin', 1)}/{NA}", KY.get(r.get("ky"), r.get("ky")), "; ".join(r["neg"])])
            ws.row_dimensions[ws.max_row].outline_level = 1
            if dem:
                written[r["keyword"]] = written.get(r["keyword"], 0) + 1

    t = wb.create_sheet("Tom tat")
    for line in [[ten], []] + tom_tat:
        t.append(line)
    t["A1"].font = Font(bold=True, size=13)
    t.column_dimensions["A"].width = 24
    t.column_dimensions["B"].width = 120

    # ---- Tầng 1: từng ASIN
    for a, ta in res.get("tung_asin", {}).items():
        ws = wb.create_sheet(f"1. {a}")
        dau(ws)
        for sheet in THU_TU_SHEET:
            ds = sorted(ta["bien_the"][sheet], key=lambda v: (_rk(v), -v["sv"]))
            muc(ws, f"{a} · kỳ {KY.get(ta['ky'], ta['ky'])} · {TEN_SHEET[sheet]}: {len(ds)} " +
                (f"biến thể (rút từ kw {TEN_SHEET[sheet]} rank 1–100 của ASIN này)" if sheet in GOC else "khối"))
            rs = [d for d in ta["rows"] if d["sheet"] == sheet]
            for v in ds:
                b = [d for d in rs if d["khoi"] == v["ten"]]
                if b:
                    khoi(ws, v["ten"], b, f"rank tốt nhất {v['rank']} · root: {v['root']}", F_V, rank=v["rank"])
            for kh, f in (("chưa phân loại", F_X), ("Khác", F_X), ("Loại bỏ (negative)", F_K)):
                b = [d for d in rs if d["khoi"] == kh]
                if b:
                    khoi(ws, kh, b, "", f)

    # ---- Tầng 2: so giữa các ASIN
    wv = wb.create_sheet("2. So sanh ASIN")
    for sheet, ds in res["bien_the"].items():
        if wv.max_row > 1:
            wv.append([])
        wv.append([f"{TEN_SHEET[sheet]}: xếp theo số ASIN dùng chung (nhiều → ít), rồi rank tốt nhất"])
        wv.cell(wv.max_row, 1).font = Font(bold=True, size=12)
        wv.append(["Biến thể", "Số ASIN dùng", "Nhóm", "Rank tốt nhất"] + [f"Rank {a}" for a in asins] +
                  ["Tổng SV", "Số kw", "Mức sát", "Bậc lọc", "Root (kw rank tốt nhất)"])
        for c in wv[wv.max_row]:
            c.font = B
        for v in sorted(ds, key=lambda v: (-v["so_asin"], _rk(v), -v["sv"])):
            wv.append([v["ten"], f"{v['so_asin']}/{NA}", v["muc"], v["rank"]] +
                      [(v["per"][a] or {}).get("rank") for a in asins] +
                      [v["sv"], v["so_kw"], f"{v['sat']}/5 {TEN_SAT[v['sat']]}" + (f" · {danh_gia[v['ten']]}" if danh_gia.get(v["ten"]) else ""), _bac_ten(v, sheet),
                       _root(v)])
    for col, w in zip("ABCDEFGHIJKLM", (28, 12, 9, 12) + (14,) * NA + (10, 8, 18, 12, 40)):
        wv.column_dimensions[col].width = w

    # ---- Tầng 3: chọn cho sản phẩm
    chon, bo = xep_uu_tien(res["bien_the"], danh_gia, loai)
    ws = wb.create_sheet("3. Chon cho SP")
    dau(ws)
    muc_cu = None
    for i, v in enumerate(chon, 1):
        v["thu_tu"] = i
        if (v["sheet"], v["muc"]) != muc_cu:
            muc(ws, f"{TEN_SHEET[v['sheet']]} · {v['muc']}" + (" (rank tốt nhất > 50)" if v["muc"] == "Cần xem xét" else ""))
            muc_cu = (v["sheet"], v["muc"])
        b = [r for r in rows if r["sheet"] == v["sheet"] and r["khoi"] == v["ten"]]
        khoi(ws, f"{v['ten']}  ({TEN_SHEET[v['sheet']]})", b,
             f"{v['so_asin']}/{NA} ASIN · rank tốt nhất {v['rank'] if v['rank'] is not None else '—'}" + (f" · {v['nhan']}" if v["nhan"] else ""), F_V, rank=v["rank"])
    if bo:
        muc(ws, "Loại: biến thể không sát sản phẩm")
        for v in bo:
            b = [r for r in rows if r["sheet"] == v["sheet"] and r["khoi"] == v["ten"]]
            khoi(ws, f"{v['ten']}  ({TEN_SHEET[v['sheet']]})", b,
                 f"{v['so_asin']}/{NA} ASIN · rank tốt nhất {v['rank']} · {v['nhan']}", F_X, rank=v["rank"])

    # ---- Bảng chia đủ (kiểm mỗi kw đúng 1 lần)
    for sheet in THU_TU_SHEET:
        ws = wb.create_sheet(TEN_SHEET[sheet].upper())
        dau(ws)
        rs = [r for r in rows if r["sheet"] == sheet]
        if sheet in GOC:
            for v in sorted(res["bien_the"][sheet], key=lambda v: (-v["so_asin"], _rk(v), -v["sv"])):
                b = [r for r in rs if r["khoi"] == v["ten"]]
                if b:
                    nhan = danh_gia.get(v["ten"])
                    khoi(ws, v["ten"], b, f"{v['so_asin']}/{NA} ASIN · {v['muc']}" + (f" · {nhan}" if nhan else ""),
                         F_V, rank=v["rank"], dem=True)
        else:
            for w in (FUNC_WORDS if sheet == "FUNCTION" else SEASON_WORDS):
                b = [r for r in rs if r["khoi"] == w]
                if b:
                    khoi(ws, w, b, sheet.title(), F_V, dem=True)
        for kh, f in (("chưa phân loại", F_X), ("Khác", F_X), ("Loại bỏ (negative)", F_K)):
            b = [r for r in rs if r["khoi"] == kh]
            if b:
                khoi(ws, kh, b, "", f, dem=True)
    ws = wb.create_sheet("Ngoai bo loc")
    dau(ws)
    b = [r for r in rows if r["sheet"] == "Ngoai bo loc"]
    if b:
        khoi(ws, "Ngoài bộ lọc", b, "", F_X, dem=True)

    for ws in wb.worksheets:
        for row in ws.iter_rows(min_row=2):
            for c in row:
                c.alignment = Alignment(vertical="top")
    wb.save(path)
    tong = len({r["keyword"] for r in rows})
    return {"tong": tong, "ghi": sum(written.values()), "trung": sum(1 for v in written.values() if v > 1),
            "thieu": tong - len(written), "chon": [(v["thu_tu"], v["ten"], v["sheet"], v["so_asin"], v["rank"]) for v in chon],
            "loai": [v["ten"] for v in bo]}


def ket_qua_json(res: dict, danh_gia: dict | None = None, loai: set | None = None) -> dict:
    """Kết quả 3 tầng dạng JSON cho trang /kw-list (không cần openpyxl)."""
    danh_gia, loai = danh_gia or {}, loai or set()
    NA, asins = res["NA"], res["asins"]
    gon = lambda r: {"keyword": r["keyword"], "sv": r["sv"], "trend": r["trend"], "rank": r["rank"], "asin": r["asin"],
                     "so_asin": r.get("so_asin", 1), "ky": r.get("ky"), "neg": r["neg"]}
    xep_kw = lambda rs: sorted(rs, key=lambda r: (-(r["sv"] or 0), r["rank"] if r["rank"] is not None else 9e9))   # SV cao trước
    khoi = lambda rs, sheet, ten: [gon(r) for r in xep_kw([r for r in rs if r["sheet"] == sheet and r["khoi"] == ten])]
    rows = res["rows"]

    tung = []
    for a, ta in res.get("tung_asin", {}).items():
        cac = {}
        for sheet, ds in ta["bien_the"].items():
            cac[sheet] = [{"ten": v["ten"], "rank": v["rank"], "root": v["root"], "so_kw": v["so_kw"], "sv": v["sv"],
                           "kw": khoi(ta["rows"], sheet, v["ten"])} for v in sorted(ds, key=lambda v: (_rk(v), -v["sv"]))]
            for kh in PHU:
                kw = khoi(ta["rows"], sheet, kh)
                if kw:
                    cac[sheet].append({"ten": kh, "rank": None, "root": None, "so_kw": len(kw),
                                       "sv": sum(r["sv"] or 0 for r in kw), "kw": kw, "phu": True})
        tung.append({"asin": a, "ky": ta["ky"], "bien_the": cac})

    so_sanh = {sheet: [{"ten": v["ten"], "so_asin": v["so_asin"], "nhom": v["nhom"], "muc": v["muc"], "rank": v["rank"],
                        "sat": v["sat"], "doi_tuong": v.get("doi_tuong", False),
                        "per": {a: (v["per"][a] or {}).get("rank") for a in asins}, "sv": v["sv"], "so_kw": v["so_kw"],
                        "bac": _bac_ten(v, sheet), "nhan": danh_gia.get(v["ten"], ""),
                        "root": _root(v)}
                       for v in sorted(ds, key=lambda v: (-v["so_asin"], _rk(v), -v["sv"]))]
               for sheet, ds in res["bien_the"].items()}

    chon, bo = xep_uu_tien(res["bien_the"], danh_gia, loai)
    the = lambda v, i=None: {"thu_tu": i, "ten": v["ten"], "sheet": v["sheet"], "so_asin": v["so_asin"], "rank": v["rank"],
                             "nhom": v["nhom"], "muc": v["muc"], "sat": v["sat"], "doi_tuong": v.get("doi_tuong", False),
                             "per": {a: (v["per"][a] or {}).get("rank") for a in asins}, "sv": v["sv"], "so_kw": v["so_kw"],
                             "nhan": v["nhan"], "kw": khoi(rows, v["sheet"], v["ten"])}
    # khối phụ của từng loại: kw chưa vào biến thể nào / dính negative, để soát tay
    phu = {sheet: [{"ten": kh, "kw": kw} for kh in PHU if (kw := khoi(rows, sheet, kh))]
           for sheet in THU_TU_SHEET}
    dem = {}
    for r in rows:
        dem.setdefault(r["sheet"], {}).setdefault(r["khoi"], 0)
        dem[r["sheet"]][r["khoi"]] += 1
    return {"NA": NA, "asins": asins, "tung_asin": tung, "so_sanh": so_sanh,
            "chon": [the(v, i) for i, v in enumerate(chon, 1)], "loai": [the(v) for v in bo], "phu": phu,
            "thu_tu_sheet": THU_TU_SHEET, "ten_sheet": TEN_SHEET, "xem_xet": RANK_XEM_XET, "ten_sat": TEN_SAT,
            "dem": dem, "tong": len({r["keyword"] for r in rows})}
