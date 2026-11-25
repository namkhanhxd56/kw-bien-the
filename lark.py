"""
Đọc / ghi Lark Base. Hai đường, tự chọn:
  - openapi: có LARK_APP_ID + LARK_APP_SECRET (khi deploy Railway, không có lark-cli).
             Gọi Open API bằng tenant token của app; app phải được thêm vào Base.
  - lark-cli: mặc định ở máy (danh tính user đã đăng nhập lark-cli).

Bảng nguồn: "PPC - Phân tích Keyword". Ảnh trong bảng này chỉ là lookup (không tải được),
nên ảnh thật lấy từ cột "Ảnh main" của bảng "🌼 2026 Product Flow", khớp theo Mã nội bộ.

Quota: tenant có hạn mức API theo tháng; tải ảnh tốn lượt media. Ảnh tải 1 lần rồi cache
trên đĩa, danh sách sản phẩm cache trong RAM cho tới khi bấm "Tải lại".
"""

from __future__ import annotations

import json
import os
import random
import re
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE = os.environ.get("LARK_BASE", "B53NbhHkBajDp5sKCTQjM96wpTc")
TABLE = os.environ.get("LARK_TABLE", "tblfV1JMXzQWifcp")          # PPC - Phân tích Keyword
VIEW = os.environ.get("LARK_VIEW", "vewB6dmunC")
# Mặc định đọc CẢ BẢNG, không theo view: ai đó đặt filter trên view Lark (25/11/2026: "Link bộ Keyword trống")
# là danh sách mã trong tool bị thu lại theo (1.850 → 86 mã). Đặt LARK_THEO_VIEW=1 nếu thật sự muốn đọc theo view.
THEO_VIEW = os.environ.get("LARK_THEO_VIEW", "").strip() in ("1", "true", "yes")
FLOW_TABLE = os.environ.get("LARK_FLOW_TABLE", "tblgYQwrwcFLwX5i")  # 🌼 2026 Product Flow
CLI = os.environ.get("LARK_CLI", "lark-cli")
APP_ID = os.environ.get("LARK_APP_ID", "").strip()
APP_SECRET = os.environ.get("LARK_APP_SECRET", "").strip()
OPEN = os.environ.get("LARK_OPEN_URL", "https://open.larksuite.com").rstrip("/")
BACKEND = "openapi" if APP_ID and APP_SECRET else "lark-cli"

F_MA = "Mã nội bộ"
F_ANH = "Hình ảnh"
F_CHAT_LIEU = "Chất liệu"
F_TEN_MAU = "Tên mẫu"
F_NICHE = "Niche"
F_ASIN_MAU = "ASIN mẫu"
F_ASIN_DT = "ASIN đối thủ (>=3)"
F_LINK = "Link bộ Keyword"
F_BIEN_THE = "Các biến thể"
F_ANH_MAIN = "Ảnh main"

ASIN_RE = re.compile(r"\bB0[A-Z0-9]{8}\b")


class LarkError(Exception):
    pass


def _run(args: list[str], cwd: Path | None = None) -> dict:
    try:
        p = subprocess.run([CLI, *args, "--as", "user"], capture_output=True, text=True,
                           timeout=120, cwd=str(cwd) if cwd else None)
    except FileNotFoundError:
        raise LarkError("Không tìm thấy lark-cli trên máy chạy server")
    except subprocess.TimeoutExpired:
        raise LarkError("lark-cli quá 120 giây không trả lời")
    out = p.stdout.strip() or p.stderr.strip()
    try:
        d = json.loads(out)
    except json.JSONDecodeError:
        raise LarkError(f"lark-cli trả về không phải JSON: {out[:300]}")
    if not d.get("ok"):
        err = d.get("error") or {}
        msg = err.get("message") or json.dumps(err, ensure_ascii=False)[:300]
        if "99991403" in json.dumps(d):
            msg = "Hết hạn mức API Lark tháng này (99991403). Dừng lại, chờ sang tháng."
        raise LarkError(msg)
    return d.get("data") or {}


# ------------------------------------------------------------ Open API (khi deploy)
_tok = {"value": "", "exp": 0.0}
_tok_khoa = threading.Lock()
QUA_TAI = {1254290, 1254291, 99991400}   # Lark chặn theo tần suất: đợi rồi thử lại
SO_LAN = 4


def _nghi(lan: int) -> None:
    time.sleep((0.4, 1.2, 3.0)[min(lan, 2)] * (1 + random.random()))


def _bao_loi(code, msg) -> str:
    if str(code) == "99991403" or "99991403" in str(msg):
        return "Hết hạn mức API Lark tháng này (99991403). Dừng lại, chờ sang tháng."
    return f"{code} {msg}"


def _http(method: str, url: str, payload=None, headers=None, raw=False):
    data = json.dumps(payload).encode() if payload is not None else None
    h = {"Content-Type": "application/json; charset=utf-8", **(headers or {})}
    for lan in range(SO_LAN):
        con = lan + 1 < SO_LAN
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=data, method=method, headers=h),
                                        timeout=60) as r:
                body = r.read()
        except urllib.error.HTTPError as e:
            if e.code == 429 and con:
                _nghi(lan)
                continue
            txt = ""
            try:
                txt = e.read().decode()[:300]
            except Exception:  # noqa: BLE001
                pass
            raise LarkError(f"Lark HTTP {e.code}: {txt}") from None
        except Exception as e:  # noqa: BLE001
            raise LarkError(f"Không gọi được Lark: {e}") from None
        if raw:
            return body
        try:
            d = json.loads(body)
        except json.JSONDecodeError:
            raise LarkError(f"Lark trả về không phải JSON: {body[:200]!r}") from None
        if d.get("code") not in (0, None):
            if (d.get("code") in QUA_TAI or "toomanyrequest" in str(d.get("msg")).lower()) and con:
                _nghi(lan)
                continue
            raise LarkError(_bao_loi(d.get("code"), d.get("msg")))
        return d
    raise LarkError("Lark chặn vì quá tải, đã thử nhiều lần. Đợi một lát rồi thử lại.")


def _token() -> str:
    with _tok_khoa:
        if _tok["value"] and time.time() < _tok["exp"]:
            return _tok["value"]
        d = _http("POST", f"{OPEN}/open-apis/auth/v3/tenant_access_token/internal",
                  {"app_id": APP_ID, "app_secret": APP_SECRET})
        _tok.update(value=d["tenant_access_token"], exp=time.time() + int(d.get("expire", 7200)) - 300)
        return _tok["value"]


def _api(method: str, path: str, payload=None) -> dict:
    return _http(method, OPEN + path, payload, {"Authorization": f"Bearer {_token()}"}).get("data") or {}


def _search(table: str, body: dict):
    """records/search, tự phân trang → [(record_id, {tên field: giá trị})]."""
    out, page = [], None
    while True:
        q = "?page_size=500" + (f"&page_token={urllib.parse.quote(page)}" if page else "")
        d = _api("POST", f"/open-apis/bitable/v1/apps/{BASE}/tables/{table}/records/search{q}", body)
        out += [(it.get("record_id"), it.get("fields") or {}) for it in d.get("items") or []]
        if not d.get("has_more"):
            return out
        page = d.get("page_token")


_field_ids: dict[tuple[str, str], str] = {}


def _field_id(table: str, name: str) -> str:
    if (table, name) not in _field_ids:
        page = None
        while True:
            q = "?page_size=100" + (f"&page_token={urllib.parse.quote(page)}" if page else "")
            d = _api("GET", f"/open-apis/bitable/v1/apps/{BASE}/tables/{table}/fields{q}")
            for f in d.get("items") or []:
                _field_ids[(table, f.get("field_name"))] = f.get("field_id")
            if not d.get("has_more"):
                break
            page = d.get("page_token")
    return _field_ids.get((table, name), "")


def _view() -> dict:
    return {"view_id": VIEW} if THEO_VIEW else {}


def _rows() -> list[tuple[str, dict]]:
    """Mọi dòng của bảng (hoặc view nguồn nếu LARK_THEO_VIEW=1) → [(record_id, {tên field: giá trị})]."""
    if BACKEND == "openapi":
        return _search(TABLE, {**_view(), "automatic_fields": False})
    rows, offset = [], 0
    while True:
        d = _run(["base", "+record-list", "--base-token", BASE, "--table-id", TABLE,
                  *(["--view-id", VIEW] if THEO_VIEW else []), "--limit", "200", "--offset", str(offset), "--format", "json"])
        names = d.get("fields") or []
        rows += [(rid, dict(zip(names, row))) for rid, row in zip(d.get("record_id_list") or [], d.get("data") or [])]
        if not d.get("has_more"):
            return rows
        offset += 200


def _text(v) -> str:
    """Ô lookup/text có thể là chuỗi, list chuỗi, hoặc list object có 'text'/'name'."""
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, list):
        return " ".join(x for x in (_text(i) for i in v) if x)
    if isinstance(v, dict):
        return _text(v.get("text") or v.get("name") or v.get("value"))
    return str(v)


def parse_asins(raw: str) -> tuple[list[str], list[str]]:
    """Tách ô ASIN đối thủ → (danh sách không trùng giữ thứ tự, các ASIN bị trùng)."""
    seen, out, dup = set(), [], []
    for a in ASIN_RE.findall((raw or "").upper()):
        if a in seen:
            dup.append(a)
            continue
        seen.add(a)
        out.append(a)
    return out, dup


_cache = {"at": 0.0, "items": []}
_khoa = threading.Lock()
CACHE_FILE: Path | None = None   # server đặt: lưu danh sách mã xuống ổ, khởi động lại thì hiện ngay


def list_products(refresh: bool = False) -> list[dict]:
    if not refresh and not _cache["items"] and CACHE_FILE and CACHE_FILE.is_file():
        # Vừa khởi động lại: dùng bản đã lưu cho nhanh, đọc lại Lark ngầm phía sau
        try:
            d = json.loads(CACHE_FILE.read_text("utf-8"))
            with _khoa:
                if not _cache["items"]:
                    _cache.update(at=d["at"], items=d["items"])
                    threading.Thread(target=_doc_lai_ngam, daemon=True).start()
        except (OSError, ValueError, KeyError):
            pass
    with _khoa:
        if _cache["items"] and not refresh:
            return _cache["items"]
        items = [it for it in (_item(rid, cell) for rid, cell in _rows()) if it]
        _cache.update(at=time.time(), items=items)
        _luu_cache()
        return items


def _item(rid: str, cell: dict) -> dict | None:
    ma = _text(cell.get(F_MA))
    if not ma:
        return None
    asins, dup = parse_asins(_text(cell.get(F_ASIN_DT)))
    return {
        "record_id": rid,
        "ma": ma,
        "ten_mau": _text(cell.get(F_TEN_MAU)),
        "niche": _text(cell.get(F_NICHE)),
        "chat_lieu": _text(cell.get(F_CHAT_LIEU)),
        "asin_mau": _text(cell.get(F_ASIN_MAU)),
        "asin_doi_thu": asins,
        "asin_trung": dup,
        "link_kw": _text(cell.get(F_LINK)),
        "bien_the": _text(cell.get(F_BIEN_THE)),
        "co_anh": bool(_text(cell.get(F_ANH))),
    }


def _luu_cache() -> None:
    """Gọi khi đang giữ _khoa."""
    if not CACHE_FILE:
        return
    try:
        tmp = CACHE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps({"at": _cache["at"], "items": _cache["items"]}, ensure_ascii=False), "utf-8")
        tmp.replace(CACHE_FILE)
    except OSError:
        pass


def _rows_cua_ma(ma: str) -> list[tuple[str, dict]]:
    """Các dòng của một mã trong view nguồn (thường 1 dòng) → [(record_id, {tên field: giá trị})]. Tốn 1 lượt API."""
    if BACKEND == "openapi":
        return _search(TABLE, {**_view(), "automatic_fields": False, "filter": {
            "conjunction": "and", "conditions": [{"field_name": F_MA, "operator": "is", "value": [ma]}]}})
    # lark-cli (ở máy): đọc theo record_id đã biết trong danh sách
    rids = [p["record_id"] for p in _cache["items"] if p["ma"] == ma]
    if not rids:
        raise LarkError(f"Mã {ma} chưa có trong danh sách, bấm Tải lại từ Lark để đọc cả bảng")
    args = ["base", "+record-get", "--base-token", BASE, "--table-id", TABLE, "--format", "json"]
    for r in rids:
        args += ["--record-id", r]
    d = _run(args)
    names = d.get("fields") or []
    return [(rid, dict(zip(names, row))) for rid, row in zip(d.get("record_id_list") or [], d.get("data") or [])]


def reload_product(ma: str) -> dict | None:
    """Đọc lại MỘT mã từ Lark và thay vào danh sách đang nhớ (khỏi đọc lại ~1.500 dòng).
    Trả về bản mới, hoặc None nếu mã không còn trong view nguồn (đã xoá khỏi danh sách)."""
    ma = ma.strip()
    list_products()   # bảo đảm đã có danh sách (và record_id cho đường lark-cli)
    moi = [it for it in (_item(rid, cell) for rid, cell in _rows_cua_ma(ma)) if it and it["ma"] == ma]
    with _khoa:
        items, chen = [], False
        for p in _cache["items"]:
            if p["ma"] != ma:
                items.append(p)
            elif not chen:   # giữ đúng vị trí cũ của mã trong thứ tự Lark
                items += moi
                chen = True
        if not chen:
            items += moi     # mã mới thêm trên Lark: tạm đặt cuối, Tải lại cả bảng sẽ xếp đúng thứ tự
        _cache["items"] = items
        _luu_cache()
    return moi[0] if moi else None


def _doc_lai_ngam() -> None:
    try:
        list_products(refresh=True)
    except Exception as e:  # noqa: BLE001
        print(f"  lark: đọc lại danh sách mã ngầm lỗi: {e}", flush=True)


def find_product(ma: str) -> dict | None:
    for p in list_products():
        if p["ma"] == ma:
            return p
    return None


_anh_khoa: dict[str, threading.Lock] = {}


def image_path(ma: str, data_dir: Path, download: bool = True) -> Path | None:
    """Ảnh main của mã. Có cache thì trả luôn; không thì tải từ Product Flow (tốn 2 lượt API)."""
    if not re.fullmatch(r"[A-Za-z0-9_-]+", ma):
        return None
    img_dir = data_dir / "img"
    img_dir.mkdir(parents=True, exist_ok=True)
    for f in img_dir.glob(f"{ma}.*"):
        return f
    if not download:
        return None
    lock = _anh_khoa.setdefault(ma, threading.Lock())
    with lock:
        for f in img_dir.glob(f"{ma}.*"):
            return f
        if BACKEND == "openapi":
            return _tai_anh_openapi(ma, data_dir)
        flt = json.dumps({"logic": "and", "conditions": [[F_MA, "==", ma]]}, ensure_ascii=False)
        d = _run(["base", "+record-list", "--base-token", BASE, "--table-id", FLOW_TABLE,
                  "--field-id", F_MA, "--field-id", F_ANH_MAIN, "--filter-json", flt,
                  "--limit", "5", "--format", "json"])
        names = d.get("fields") or []
        for rid, row in zip(d.get("record_id_list") or [], d.get("data") or []):
            files = dict(zip(names, row)).get(F_ANH_MAIN) or []
            if not files:
                continue
            f0 = files[0]
            ext = (Path(f0.get("name") or "").suffix or ".jpg").lower()
            rel = f"img/{ma}{ext}"
            # lark-cli chỉ nhận đường dẫn tương đối trong thư mục đang đứng
            _run(["base", "+record-download-attachment", "--base-token", BASE,
                  "--table-id", FLOW_TABLE, "--record-id", rid,
                  "--file-token", f0["file_token"], "--output", rel, "--overwrite"], cwd=data_dir)
            p = data_dir / rel
            return p if p.exists() else None
        return None


def _tai_anh_openapi(ma: str, data_dir: Path) -> Path | None:
    rows = _search(FLOW_TABLE, {"field_names": [F_MA, F_ANH_MAIN], "automatic_fields": False,
                                "filter": {"conjunction": "and", "conditions": [
                                    {"field_name": F_MA, "operator": "is", "value": [ma]}]}})
    for rid, cell in rows:
        files = [f for f in (cell.get(F_ANH_MAIN) or []) if isinstance(f, dict) and f.get("file_token")]
        if not files:
            continue
        f0 = files[0]
        ext = (Path(f0.get("name") or "").suffix or ".jpg").lower()
        # Ảnh trong Base phải kèm "extra" (bitablePerm) mới tải được bằng tenant token
        goc = f"{OPEN}/open-apis/drive/v1/medias/{f0['file_token']}/download"
        duong = []
        fid = _field_id(FLOW_TABLE, F_ANH_MAIN)
        if fid:
            extra = json.dumps({"bitablePerm": {"tableId": FLOW_TABLE,
                                                "attachments": {fid: {rid: [f0["file_token"]]}}}},
                               separators=(",", ":"))
            duong.append(goc + "?extra=" + urllib.parse.quote(extra, safe=""))
        duong.append(goc)
        loi = None
        for u in duong:
            try:
                body = _http("GET", u, headers={"Authorization": f"Bearer {_token()}"}, raw=True)
            except LarkError as e:
                loi = e
                continue
            p = data_dir / "img" / f"{ma}{ext}"
            p.write_bytes(body)
            return p
        if loi:
            raise loi
    return None


def write_link(record_id: str, url: str) -> None:
    if BACKEND == "openapi":
        _api("POST", f"/open-apis/bitable/v1/apps/{BASE}/tables/{TABLE}/records/batch_update",
             {"records": [{"record_id": record_id, "fields": {F_LINK: url}}]})
    else:
        body = json.dumps({"update_records": {record_id: {F_LINK: url}}}, ensure_ascii=False)
        _run(["base", "+record-batch-update", "--base-token", BASE, "--table-id", TABLE,
              "--json", body])
    for p in _cache["items"]:
        if p["record_id"] == record_id:
            p["link_kw"] = url
