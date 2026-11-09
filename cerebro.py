"""
Đọc file Cerebro (xlsx/csv) và chuẩn hoá dòng keyword — không cần openpyxl.

File Cerebro có nhiều kiểu cột (13 / 15 / 16 / 26 cột); chỉ cần tìm được 4 cột:
Keyword Phrase, Search Volume, Search Volume Trend, Organic Rank (hoặc "Organic Rank (avg)").
"""

from __future__ import annotations

import csv
import html
import io
import re
import zipfile

ASIN_RE = re.compile(r"B0[A-Z0-9]{8}")

COT_KW = ["keyword phrase", "keyword"]
COT_SV = ["search volume"]
COT_TREND = ["search volume trend"]
COT_RANK = ["organic rank", "organic rank (avg)"]


class LoiFile(Exception):
    pass


def _xlsx_rows(data: bytes) -> list[list[str]]:
    """Sheet đầu tiên (Cerebro đặt tên 'Table') → list dòng."""
    z = zipfile.ZipFile(io.BytesIO(data))
    with z:
        try:
            raw = z.read("xl/sharedStrings.xml").decode("utf-8", "replace")
            shared = [html.unescape("".join(re.findall(r"<t[^>]*>(.*?)</t>", si, re.S)))
                      for si in re.findall(r"<si>(.*?)</si>", raw, re.S)]
        except KeyError:
            shared = []
        sheets = sorted(n for n in z.namelist() if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n))
        if not sheets:
            raise LoiFile("File xlsx không có sheet nào")
        xml = z.read(sheets[0]).decode("utf-8", "replace")
    rows = []
    for rm in re.finditer(r"<row\b[^>]*>(.*?)</row>", xml, re.S):
        cells = {}
        for cm in re.finditer(r'<c\b([^>]*?)(?:/>|>(.*?)</c>)', rm.group(1), re.S):
            attrs, inner = cm.group(1), cm.group(2) or ""
            ref = re.search(r'r="([A-Z]+)\d+"', attrs)
            if not ref:
                continue
            col = 0
            for ch in ref.group(1):
                col = col * 26 + ord(ch) - 64
            if 't="inlineStr"' in attrs:
                val = html.unescape("".join(re.findall(r"<t[^>]*>(.*?)</t>", inner, re.S)))
            else:
                v = re.search(r"<v>(.*?)</v>", inner, re.S)
                if not v:
                    val = ""
                elif 't="s"' in attrs:
                    k = int(v.group(1))
                    val = shared[k] if 0 <= k < len(shared) else ""
                else:
                    val = html.unescape(v.group(1))
            cells[col] = val
        if cells:
            rows.append([cells.get(i, "") for i in range(1, max(cells) + 1)])
    return rows


def _csv_rows(data: bytes) -> list[list[str]]:
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    first = text.split("\n", 3)[:3]
    delim = max([",", ";", "\t"], key=lambda d: sum(l.count(d) for l in first))
    return list(csv.reader(io.StringIO(text), delimiter=delim))


def _norm(s) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip().lower()


def _so(v):
    s = str(v if v is not None else "").strip().replace(",", "")
    if s in ("", "-", "N/A", "n/a"):
        return None
    try:
        f = float(s.lstrip("><=~ "))
    except ValueError:
        return None
    return int(f) if f.is_integer() else f


def _cot(header: list[str], ten: list[str]):
    h = [_norm(x) for x in header]
    for t in ten:
        if t in h:
            return h.index(t)
    return None


def norm_kw(k) -> str:
    """Khoá so trùng: viết thường, bỏ ký tự ngoài ASCII, bỏ khoảng trắng thừa."""
    return " ".join(str(k or "").lower().encode("ascii", "ignore").decode().split())


def chuan_hoa(raw: list[dict]) -> list[dict]:
    """Dòng do extension gửi lên (JSON) → cùng dạng với dòng đọc từ file."""
    out = []
    for r in raw:
        kw = str(r.get("keyword") or r.get("Keyword Phrase") or "").strip()
        if not kw:
            continue
        out.append({
            "keyword": kw,
            "sv": _so(r.get("search_volume", r.get("Search Volume"))),
            "trend": _so(r.get("search_volume_trend", r.get("Search Volume Trend"))),
            "rank": _so(r.get("organic_rank", r.get("Organic Rank"))),
        })
    return out


def doc_file(data: bytes, ten_file: str) -> list[dict]:
    if data[:2] == b"PK":
        rows = _xlsx_rows(data)
    else:
        rows = _csv_rows(data)
    hi = next((i for i, r in enumerate(rows[:10]) if _cot(r, COT_KW) is not None), None)
    if hi is None:
        raise LoiFile("Không thấy cột 'Keyword Phrase' — có phải file Cerebro không?")
    h = rows[hi]
    ck, cs, ct, cr = _cot(h, COT_KW), _cot(h, COT_SV), _cot(h, COT_TREND), _cot(h, COT_RANK)
    if cs is None or cr is None:
        raise LoiFile("Thiếu cột Search Volume hoặc Organic Rank")
    out = []
    for r in rows[hi + 1:]:
        g = lambda c: r[c] if c is not None and c < len(r) else ""
        kw = str(g(ck)).strip()
        if not kw:
            continue
        out.append({"keyword": kw, "sv": _so(g(cs)), "trend": _so(g(ct)), "rank": _so(g(cr))})
    return out


def kiem_bo_loc(rows: list[dict], sv_min: int, rank_min: int) -> list[str]:
    """Cảnh báo khi file không khớp bộ lọc chuẩn (SV, organic rank)."""
    canh_bao = []
    sv_thap = sum(1 for r in rows if r["sv"] is None or r["sv"] < sv_min)
    khong_rank = sum(1 for r in rows if r["rank"] is None or r["rank"] < rank_min)
    if sv_thap:
        canh_bao.append(f"{sv_thap} dòng có Search Volume dưới {sv_min}")
    if khong_rank:
        canh_bao.append(f"{khong_rank} dòng không có organic rank (hoặc < {rank_min})")
    return canh_bao


def gop(theo_asin: dict[str, dict]) -> tuple[list[dict], dict]:
    """Gộp nhiều ASIN: mỗi keyword giữ 1 dòng thắng — organic rank nhỏ nhất,
    dòng không rank thua mọi dòng có rank, hoà rank thì SV cao hơn thắng."""
    tot = {}
    goc = 0
    for asin, info in theo_asin.items():
        for r in info.get("rows") or []:
            goc += 1
            k = norm_kw(r["keyword"])
            if not k:
                continue
            cand = {**r, "asin": asin, "ky": info.get("period_used"), "cac_asin": [asin]}
            cur = tot.get(k)
            if cur is None:
                tot[k] = cand
                continue
            cur_key = (cur["rank"] is None, cur["rank"] or 0, -(cur["sv"] or 0))
            new_key = (cand["rank"] is None, cand["rank"] or 0, -(cand["sv"] or 0))
            cac = cur["cac_asin"] + ([asin] if asin not in cur["cac_asin"] else [])
            tot[k] = {**(cand if new_key < cur_key else cur), "cac_asin": cac}
    rows = sorted(tot.values(), key=lambda r: (-(r["sv"] or 0), r["keyword"]))
    for r in rows:
        r["so_asin"] = len(r["cac_asin"])
    return rows, {"goc": goc, "gop": len(rows), "trung": goc - len(rows)}
