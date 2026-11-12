#!/usr/bin/env python3
"""
KW Biến Thể — bản tạm: lấy keyword ASIN đối thủ từ Cerebro (H10) cho từng mã trên Lark.

Luồng (giai đoạn này): chọn mã trên Lark → xem ảnh (chỉ tin ảnh) → ghi phân tích sơ bộ
→ tạo bộ keyword {Mã}-{niche product} → xếp job Cerebro cho từng ASIN đối thủ
→ extension lấy về (hoặc tải file tay) → trang /kw-list/<tên bộ> → ghi link về Lark.
Chia biến thể là bước sau, chưa có ở đây.

Chạy:  HOST=127.0.0.1 PORT=8796 python3 -u server.py

Biến môi trường:
  HOST / PORT       mặc định 127.0.0.1:8796; có PORT mà không có HOST (Railway) thì 0.0.0.0.
                    Bind ra ngoài cần BRO_AUTH_URL + BRO_AUTH_API_KEY, hoặc ALLOW_NO_AUTH=1 (xem auth.py).
  PUBLIC_URL        domain dựng link bộ keyword (mặc định https://$RAILWAY_PUBLIC_DOMAIN,
                    ở máy là http://localhost:<PORT>)
  DATA_DIR          nơi lưu dữ liệu (mặc định ./data)
  AGENT_TOKEN       khoá cho extension gọi /api/agent/*; trống = chỉ nhận từ localhost
  LARK_APP_ID / LARK_APP_SECRET   có thì đọc Lark bằng Open API (khi deploy), không thì lark-cli
  BRO_AUTH_URL / BRO_AUTH_API_KEY đăng nhập + phân quyền (auth.py)
  DAILY_LIMIT       số lượt Cerebro tối đa mỗi ngày (mặc định 0 = không giới hạn; H10 tự chặn thì extension dừng)
  SV_MIN / RANK_MIN / RANK_MAX  bộ lọc chuẩn (mặc định SV ≥ 50, organic rank 1–100)
  LARK_BASE, LARK_TABLE, LARK_VIEW, LARK_FLOW_TABLE   xem lark.py
"""

from __future__ import annotations

import csv
import hmac
import io
import json
import mimetypes
import os
import re
import sys
import threading
import time
import traceback
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from collections import OrderedDict
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

import auth
import cerebro
import engine
import lark
import xuat
from store import KY_CHINH, KY_HIEN_TAI, Store, thu_tu_chay

GOC = Path(__file__).resolve().parent
WEB = GOC / "web"
CAU_HINH = GOC / "cau-hinh"
NHAN = ["Sát", "Xa", "Không hợp"]   # so biến thể với sản phẩm; "Không hợp" bị loại khỏi danh sách chọn
HOST = os.environ.get("HOST", "0.0.0.0" if os.environ.get("PORT") else "127.0.0.1")
PORT = int(os.environ.get("PORT", "8796"))
_RW = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "").strip()
PUBLIC_URL = (os.environ.get("PUBLIC_URL") or (f"https://{_RW}" if _RW else f"http://localhost:{PORT}")).rstrip("/")
DATA = Path(os.environ.get("DATA_DIR", GOC / "data")).resolve()
AGENT_TOKEN = os.environ.get("AGENT_TOKEN", "").strip()
DAILY_LIMIT = int(os.environ.get("DAILY_LIMIT", "0"))


def het_luot_ngay() -> bool:
    return DAILY_LIMIT > 0 and store.usage_today() >= DAILY_LIMIT
SV_MIN = int(os.environ.get("SV_MIN", "50"))
RANK_MIN = int(os.environ.get("RANK_MIN", "1"))
RANK_MAX = int(os.environ.get("RANK_MAX", "100"))
MAX_UPLOAD = 30 * 1024 * 1024

store = Store(DATA)


_cap_cache: dict[str, tuple[int, int]] = {}   # tên file → (dung lượng đã đếm, số dòng)


def tom_tat_capture() -> list[dict]:
    """Các ngày có request do chế độ "Ghi lại" gửi về: tên file, số dòng, dung lượng.
    /api/status gọi vài giây một lần nên không đọc lại cả file: nhớ số dòng theo dung lượng, file chỉ ghi nối thêm
    nên chỉ đếm phần mới."""
    out = []
    for f in sorted((DATA / "capture").glob("*.jsonl")):
        size = f.stat().st_size
        da, so = _cap_cache.get(f.name, (0, 0))
        if size != da:
            if size < da:
                da, so = 0, 0
            with open(f, "rb") as fh:
                fh.seek(da)
                so += sum(1 for _ in fh)
            _cap_cache[f.name] = (size, so)
        out.append({"file": f.name, "so": so, "kb": round(size / 1024)})
    return out


def luu_tru() -> dict:
    """Dữ liệu có nằm trên volume không. Không có volume thì mỗi lần deploy Railway là mất hết."""
    vol = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", "").rstrip("/")
    tren_vol = bool(vol) and (str(DATA) == vol or str(DATA).startswith(vol + "/"))
    return {"data_dir": str(DATA), "volume": vol or None,
            "volume_name": os.environ.get("RAILWAY_VOLUME_NAME") or None,
            "tren_volume": tren_vol, "la_diem_gan": os.path.ismount(DATA)}

BO_LOC = {
    "period": KY_CHINH,
    "period_fallback": KY_HIEN_TAI,
    "loc_ky_hien_tai": False,   # kỳ hiện tại = sản phẩm mới (12/2025 không có keyword): không lọc SV/rank
    "exclude_variations": True,
    "search_volume_min": SV_MIN,
    "organic_rank_min": RANK_MIN,
    "organic_rank_max": RANK_MAX,
    "mot_asin_mot_lan": True,
}


def link_bo(slug: str) -> str:
    return f"{PUBLIC_URL}/kw-list/{quote(slug)}"


def trang_thai_asin(slug: str, asins: list[str], jobs: list[dict] | None = None) -> list[dict]:
    """jobs: hàng đợi đã đọc sẵn (danh sách mã truyền vào để khỏi đọc jobs.json cho từng bộ)."""
    jobs = [j for j in jobs if j["slug"] == slug] if jobs is not None else store.jobs_for(slug)
    out = []
    for a in asins:
        js = sorted((j for j in jobs if j["asin"] == a), key=lambda j: j["created_at"])
        last = js[-1] if js else None
        d = store.asin_tom_tat(slug, a)
        st = {"asin": a, "so_kw": d["so_kw"] if d else 0,
              "period_used": d["period_used"] if d else None,
              "nguon": d["nguon"] if d else None,
              "canh_bao": d.get("canh_bao", []) if d else [],
              "fetched_at": d["fetched_at"] if d else None, "loi": "",
              "dung_lai_tu": d.get("dung_lai_tu") if d else None}
        if last and last["status"] in ("queued", "running"):
            st["trang_thai"] = "cho" if last["status"] == "queued" else "dang_lay"
            st["period_dang_thu"] = last["period"]
        elif d is not None:
            st["trang_thai"] = "xong" if d["so_kw"] else "rong"
        elif last and last["status"] == "failed":
            st["trang_thai"], st["loi"] = "loi", last["error"]
        else:
            st["trang_thai"] = "chua_lay"
        out.append(st)
    return out


def bo_theo(slug_hoac_ma: str) -> dict | None:
    """Bộ keyword theo tên bộ, hoặc theo Mã sản phẩm (bộ mới nhất của mã) — để agent chỉ cần biết Mã."""
    meta = store.get_list(slug_hoac_ma)
    if meta:
        return meta
    ma = slug_hoac_ma.strip().upper()
    if time.time() - _ma_slug["luc"] > 600 or ma not in _ma_slug["bang"]:
        # Không giữ khoá của store: quét ~1.400 meta.json lâu, giữ khoá thì chặn cả hàng đợi job
        _ma_slug.update(luc=time.time(), bang={m: b["slug"] for m, b in store.lists_by_ma().items()})
    slug = _ma_slug["bang"].get(ma)
    return store.get_list(slug) if slug else None


_ma_slug = {"luc": 0.0, "bang": {}}   # Mã → tên bộ mới nhất, nhớ 10 phút để tra theo Mã khỏi quét lại


def da_xoa(slug: str) -> list[str]:
    """Keyword người dùng đã bỏ khỏi bộ (ô tích → Xoá), lưu theo bộ; khôi phục được."""
    return store._read(store.list_dir(slug) / "da_xoa.json", [])


# ---- Nhớ kết quả đọc bộ / chia biến thể: mở trang bộ keyword không phải đọc lại mọi file ASIN và chia lại
# biến thể khi dữ liệu không đổi. Khoá nhớ = mtime + dung lượng các file đầu vào; đổi file nào là tính lại.
_bo_cache: OrderedDict = OrderedDict()
_bo_cache_khoa = threading.Lock()
BO_CACHE_MAX = 24   # mỗi bộ vài MB trong RAM, giữ các bộ mở gần nhất


def _chu_ky(*paths: Path) -> tuple:
    out = []
    for p in paths:
        try:
            st = p.stat()
            out.append((st.st_mtime_ns, st.st_size))
        except FileNotFoundError:
            out.append(None)
    return tuple(out)


def _nho(slug: str, loai: str, chu_ky: tuple, tinh):
    k = (slug, loai)
    with _bo_cache_khoa:
        c = _bo_cache.get(k)
        if c and c[0] == chu_ky:
            _bo_cache.move_to_end(k)
            return c[1]
    v = tinh()
    with _bo_cache_khoa:
        _bo_cache[k] = (chu_ky, v)
        _bo_cache.move_to_end(k)
        while len(_bo_cache) > BO_CACHE_MAX:
            _bo_cache.popitem(last=False)
    return v


def _chu_ky_du_lieu(meta: dict) -> tuple:
    d = store.list_dir(meta["slug"])
    asins = tuple(meta.get("asins") or [])
    return (asins,) + _chu_ky(*(d / f"{a}.json" for a in asins), d / "da_xoa.json")


def du_lieu_bo(meta: dict) -> tuple[dict, list[dict], dict]:
    """Dữ liệu từng ASIN và dòng đã gộp của một bộ, đã bỏ các keyword người dùng xoá.
    Kết quả được nhớ và dùng chung: nơi gọi KHÔNG được sửa data / rows trả về."""
    return _nho(meta["slug"], "du_lieu", _chu_ky_du_lieu(meta), lambda: _doc_du_lieu_bo(meta))


def _doc_du_lieu_bo(meta: dict) -> tuple[dict, list[dict], dict]:
    bo = {k.lower() for k in da_xoa(meta["slug"])}
    data = {}
    for a, d in store.all_asin_data(meta["slug"], meta.get("asins") or []).items():
        data[a] = {**d, "rows": [r for r in d.get("rows") or [] if r["keyword"].lower() not in bo]}
    rows, stats = cerebro.gop(data)
    return data, rows, stats


def tom_tat_bo(meta: dict, kem_dong: bool = False, jobs: list[dict] | None = None) -> dict:
    asins = trang_thai_asin(meta["slug"], meta.get("asins") or [], jobs)
    out = {**meta, "link": link_bo(meta["slug"]), "trang_thai_asin": asins,
           "so_xong": sum(1 for a in asins if a["trang_thai"] in ("xong", "rong"))}
    if kem_dong:
        data, rows, stats = du_lieu_bo(meta)
        ky = {d["period_used"] for d in data.values() if d["rows"]}
        out.update(rows=rows, stats=stats, ky_tron=len(ky) > 1, da_xoa=da_xoa(meta["slug"]))
    return out


def cau_hinh(ma: str) -> dict:
    """Negative + nhãn so với sản phẩm cho một mã: cau-hinh/<Mã>.json nếu có, không thì negative mặc định."""
    neg = json.loads((CAU_HINH / "neg-mac-dinh.json").read_text("utf-8"))
    ch = {"neg": neg, "danh_gia": {}, "target_year": time.strftime("%Y"), "rieng": False}
    f = CAU_HINH / f"{store.slugify(ma).upper()}.json"
    if f.is_file():
        c = json.loads(f.read_text("utf-8"))
        ch.update(neg=c.get("neg") or neg, danh_gia=c.get("danh_gia") or {}, target_year=c.get("target_year") or ch["target_year"], rieng=True)
    return ch


def tinh_bien_the(meta: dict) -> dict:
    """Chia biến thể 3 tầng (engine.chia_nhom) cho một bộ keyword, nhãn người dùng sửa đè lên nhãn cấu hình.
    Nhớ theo file đầu vào (dữ liệu ASIN, keyword đã xoá, nhãn, cấu hình mã) — nơi gọi không được sửa kết quả."""
    slug = meta["slug"]
    chu_ky = (_chu_ky_du_lieu(meta) + _chu_ky(store.list_dir(slug) / "danh_gia.json", CAU_HINH / "neg-mac-dinh.json",
                                              CAU_HINH / f"{store.slugify(meta['ma']).upper()}.json")
              + (time.strftime("%Y"),))
    return _nho(slug, "bien_the", chu_ky, lambda: _chia_bien_the(meta))


def _chia_bien_the(meta: dict) -> dict:
    slug = meta["slug"]
    data, rows, stats = du_lieu_bo(meta)
    rows = [dict(r) for r in rows]   # chia_nhom ghi thêm khoá vào từng dòng: chép để không bẩn bản đang nhớ
    data = {a: d for a, d in data.items() if d.get("rows")}
    ch = cau_hinh(meta["ma"])
    dg = {**ch["danh_gia"], **store._read(store.list_dir(slug) / "danh_gia.json", {})}
    asins = [a for a in meta.get("asins") or [] if a in data]
    if not asins:
        return {"ok": True, "trong": True, "asins": [], "nhan_chon": NHAN}
    res = engine.chia_nhom(rows, asins, ch["neg"], theo_asin=data, target_year=ch["target_year"], rank_root=RANK_MAX,
                           sv_min=SV_MIN, rank_min=RANK_MIN, rank_max=RANK_MAX)
    out = engine.ket_qua_json(res, dg, {"Không hợp"})
    out.update(ok=True, stats=stats, nhan_chon=NHAN, cau_hinh_rieng=ch["rieng"], target_year=ch["target_year"],
               ky={a: data[a].get("period_used") for a in asins})
    return out


def sap_uu_tien(ds: list[str], cho: dict[str, set], dang: set) -> tuple[list[str], list[str]]:
    """Xếp ASIN của các mã cần ưu tiên → (thứ tự ASIN, thứ tự mã).
    w(ASIN) = số mã trong danh sách cùng chờ ASIN đó. Mỗi bước chọn mã có ASIN dùng chung nhiều nhất
    (rồi ít ASIN còn lại nhất để xong sớm, rồi tổng w, rồi thứ tự người dùng dán), chạy hết ASIN của mã đó
    (w cao trước) rồi mới sang mã kế. ASIN đang lấy dở không xếp lại."""
    w: dict[str, int] = {}
    for a_s in cho.values():
        for a in a_s:
            w[a] = w.get(a, 0) + 1
    xong_a, thu_tu, thu_tu_ma = set(dang), [], []
    con = [m for m in ds if m in cho]
    while con:
        def diem(m):
            r = cho[m] - xong_a
            return (max((w[a] for a in r), default=0), -len(r), sum(w[a] for a in r), -ds.index(m))
        m = max(con, key=diem)
        con.remove(m)
        r = sorted(cho[m] - xong_a, key=lambda a: (-w[a], a))
        thu_tu += r
        xong_a |= set(r)
        thu_tu_ma.append(m)
    return thu_tu, thu_tu_ma


def danh_sach_may() -> list[dict]:
    """Các máy extension đã báo về (từ lúc server chạy), máy báo gần nhất trước; kèm ASIN đang lấy."""
    now, dang = time.time(), {}
    for j in store._jobs():
        if j["status"] == "running":
            dang[j.get("may") or "may-cu"] = j["asin"]
    out = []
    for m in sorted(store.agents.values(), key=lambda x: -x["last_seen"]):
        if now - m["last_seen"] > 24 * 3600:
            continue
        out.append({**m, "online": now - m["last_seen"] < 90, "dang_lay": dang.get(m["id"])})
    return out


class Handler(BaseHTTPRequestHandler):
    server_version = "KWBienThe/0.1"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (self.log_date_time_string(), fmt % args))

    # ------------------------------------------------------------ trả lời
    def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode(), "application/json; charset=utf-8")

    def _err(self, code: int, msg: str):
        self._json({"ok": False, "error": msg}, code)

    def _file(self, p: Path):
        if not p.is_file():
            return self._err(404, "Không có file")
        ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype.endswith("javascript"):
            ctype += "; charset=utf-8"
        self._send(200, p.read_bytes(), ctype)

    def _body(self) -> bytes:
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_UPLOAD:
            raise ValueError("File quá lớn (tối đa 30MB)")
        return self.rfile.read(n) if n else b""

    def _jbody(self) -> dict:
        raw = self._body()
        return json.loads(raw) if raw else {}

    def _agent_ok(self) -> bool:
        if AGENT_TOKEN:
            return hmac.compare_digest(self.headers.get("X-Agent-Token", ""), AGENT_TOKEN)
        return self.client_address[0] in ("127.0.0.1", "::1")

    # ------------------------------------------------------------ định tuyến
    def do_GET(self):
        self._route("GET")

    def do_POST(self):
        self._route("POST")

    def _route(self, method: str):
        u = urlparse(self.path)
        path, q = unquote(u.path), parse_qs(u.query)
        try:
            if auth.handle_routes(self):          # /login, /logout
                return
            if method == "GET" and path == "/healthz":
                return self._json({"ok": True})
            if method == "GET" and path == "/api/me":
                return self._json(auth.me(self))
            ok, _sess = auth.guard(self, path, method)
            if not ok:
                return                            # guard đã tự trả 302/403
            if method == "GET":
                if path == "/":
                    return self._file(WEB / "index.html")
                if path.startswith("/kw-list/"):
                    return self._file(WEB / "kwlist.html")
                if path == "/hang-doi":
                    return self._file(WEB / "hang-doi.html")
                if path == "/extension.zip":
                    return self._extension_zip()
                if path == "/api/hang-doi":
                    return self._hang_doi()
                if path.startswith("/static/"):
                    p = (WEB / path[len("/static/"):]).resolve()
                    if WEB not in p.parents:
                        return self._err(404, "Không có file")
                    return self._file(p)
                if path == "/api/status":
                    return self._status()
                if path == "/api/products":
                    return self._products(q.get("refresh") == ["1"])
                m = re.fullmatch(r"/api/products/([^/]+)/image", path)
                if m:
                    return self._image(m.group(1), q.get("cached") != ["1"])
                m = re.fullmatch(r"/api/analysis/([^/]+)", path)
                if m:
                    return self._json({"ok": True, "analysis": store.get_analysis(m.group(1))})
                m = re.fullmatch(r"/api/lists/([^/]+)", path)
                if m:
                    meta = bo_theo(m.group(1))
                    if not meta:
                        return self._err(404, "Chưa có bộ keyword này")
                    return self._json({"ok": True, "list": {"da_xoa": da_xoa(meta["slug"]),
                                                            **tom_tat_bo(meta, kem_dong=q.get("rows") != ["0"])}})
                m = re.fullmatch(r"/api/lists/([^/]+)/export\.csv", path)
                if m:
                    return self._export(m.group(1))
                m = re.fullmatch(r"/api/lists/([^/]+)/final\.(xlsx|md)", path)
                if m:
                    return self._final(m.group(1), m.group(2), q)
                if path in ("/huong-dan-agent", "/huong-dan-agent.md"):
                    return self._send(200, (GOC / "HUONG-DAN-AGENT.md").read_bytes(), "text/markdown; charset=utf-8")
                m = re.fullmatch(r"/api/lists/([^/]+)/bien-the", path)
                if m:
                    return self._bien_the(m.group(1))
                if path == "/api/agent/next":
                    return self._agent_next()
                if path == "/api/agent/ping":
                    return self._agent_ping()
                m = re.fullmatch(r"/api/agent/captures/(\d{4}-\d{2}-\d{2}\.jsonl)", path)
                if m:
                    return self._agent_capture_file(m.group(1))
            else:
                if path == "/api/tool/dung":
                    return self._dung_tool()
                if path == "/api/hang-doi/bo":
                    return self._bo_hang_doi()
                if path == "/api/hang-doi/uu-tien":
                    return self._uu_tien()
                if path == "/api/dung-lai":
                    return self._json({"ok": True, **store.dung_lai_tat_ca()})
                if path == "/api/lists":
                    return self._create_list()
                m = re.fullmatch(r"/api/analysis/([^/]+)", path)
                if m:
                    return self._json({"ok": True, "analysis": store.save_analysis(m.group(1), self._jbody())})
                m = re.fullmatch(r"/api/lists/([^/]+)/fetch", path)
                if m:
                    return self._fetch(m.group(1))
                m = re.fullmatch(r"/api/lists/([^/]+)/cancel", path)
                if m:
                    return self._cancel(m.group(1))
                m = re.fullmatch(r"/api/lists/([^/]+)/upload", path)
                if m:
                    return self._upload(m.group(1), q)
                m = re.fullmatch(r"/api/lists/([^/]+)/lark-link", path)
                if m:
                    return self._lark_link(m.group(1))
                m = re.fullmatch(r"/api/lists/([^/]+)/bien-the/nhan", path)
                if m:
                    return self._dat_nhan(m.group(1))
                m = re.fullmatch(r"/api/lists/([^/]+)/xoa", path)
                if m:
                    return self._xoa_kw(m.group(1))
                if path == "/api/agent/capture":
                    return self._agent_capture()
                m = re.fullmatch(r"/api/agent/jobs/([a-f0-9]+)/(result|fail|release)", path)
                if m:
                    return self._agent_report(m.group(1), m.group(2))
            return self._err(404, "Không có đường dẫn này")
        except lark.LarkError as e:
            return self._err(502, f"Lark: {e}")
        except (ValueError, cerebro.LoiFile, json.JSONDecodeError) as e:
            return self._err(400, str(e))
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            return self._err(500, f"Lỗi máy chủ: {e}")

    # ------------------------------------------------------------ trang thông tin
    def _status(self):
        may = danh_sach_may()
        con = [m for m in may if m["online"]]
        # "agent" giữ dạng cũ (một máy) cho giao diện cũ: lấy máy online báo gần nhất
        dai_dien = (con or may or [{"online": False, "last_seen": None}])[0]
        self._json({
            "ok": True, "bo_loc": BO_LOC, "public_url": PUBLIC_URL,
            "commit": os.environ.get("RAILWAY_GIT_COMMIT_SHA", "")[:7] or None,   # bản đang chạy trên Railway
            "agent": {**dai_dien, "so_may": len(con)}, "may": may,
            "luot_hom_nay": store.usage_today(), "gioi_han_ngay": DAILY_LIMIT,
            "hang_doi": store.queue_size(), "tam_dung": store.tam_dung(),
            "luu_tru": luu_tru(), "capture": tom_tat_capture(),
        })

    def _products(self, refresh: bool):
        items = lark.list_products(refresh)
        bo, jobs = store.lists_by_ma(), store._jobs()
        out = []
        for p in items:
            meta = bo.get(p["ma"])
            out.append({**p, "bo": tom_tat_bo(meta, jobs=jobs) if meta else None,
                        "da_phan_tich": bool(store.get_analysis(p["ma"]).get("ket_luan")),
                        "anh_cache": lark.image_path(p["ma"], DATA, download=False) is not None})
        self._json({"ok": True, "products": out})

    def _image(self, ma: str, download: bool):
        p = lark.image_path(ma, DATA, download=download)
        if not p:
            return self._err(404, "Chưa có ảnh")
        self._file(p)

    # ------------------------------------------------------------ bộ keyword
    def _create_list(self):
        b = self._jbody()
        ma = (b.get("ma") or "").strip()
        prod = lark.find_product(ma)
        if not prod:
            raise ValueError(f"Không thấy mã {ma} trong bảng Lark")
        asins = []
        for a in b.get("asins") or []:
            a = str(a).strip().upper()
            if not lark.ASIN_RE.fullmatch(a):
                raise ValueError(f"ASIN không hợp lệ: {a}")
            if a not in asins:
                asins.append(a)
        meta = store.upsert_list(ma=ma, record_id=prod["record_id"], niche=b.get("niche", ""),
                                 product=b.get("product", ""), asins=asins)
        self._json({"ok": True, "list": tom_tat_bo(meta)})

    def _fetch(self, slug: str):
        meta = store.get_list(slug)
        if not meta:
            return self._err(404, "Chưa có bộ keyword này")
        b = self._jbody()
        chon = [a for a in (b.get("asins") or meta["asins"]) if a in meta["asins"]]
        if len(meta["asins"]) < 3:
            raise ValueError("Cần tối thiểu 3 ASIN đối thủ trước khi lấy keyword")
        lay_lai = bool(b.get("lay_lai"))
        st = {s["asin"]: s for s in trang_thai_asin(slug, meta["asins"])}
        can = [a for a in chon if lay_lai or st[a]["trang_thai"] in ("chua_lay", "loi")]
        # ASIN đã lấy ở bộ khác thì chép sang, không tốn lượt (bấm "Lấy lại" mới chạy Cerebro mới)
        dung_lai = [] if lay_lai else [a for a in can if store.dung_lai_asin(slug, a)]
        can = [a for a in can if a not in dung_lai]
        # ASIN đang chờ ở bộ khác: vẫn xếp nhưng không tốn thêm lượt, xong là điền chung
        cho_chung = store.asin_dang_cho()
        moi = [a for a in can if a not in cho_chung]
        con_lai = DAILY_LIMIT - store.usage_today() - store.queue_size()
        if DAILY_LIMIT > 0 and len(moi) > max(con_lai, 0):
            raise ValueError(f"Vượt giới hạn {DAILY_LIMIT} lượt Cerebro/ngày (còn {max(con_lai, 0)} lượt)"
                             + (f" · đã dùng lại {len(dung_lai)} ASIN từ bộ khác" if dung_lai else ""))
        for a in can:
            store.enqueue(slug, a)
        self._json({"ok": True, "xep_hang": can, "dung_lai": dung_lai, "luot_moi": len(moi),
                    "list": tom_tat_bo(meta)})

    def _cancel(self, slug: str):
        meta = store.get_list(slug)
        if not meta:
            return self._err(404, "Chưa có bộ keyword này")
        for a in self._jbody().get("asins") or meta["asins"]:
            store.cancel(slug, a)
        self._json({"ok": True, "list": tom_tat_bo(meta)})

    def _upload(self, slug: str, q: dict):
        meta = store.get_list(slug)
        if not meta:
            return self._err(404, "Chưa có bộ keyword này")
        asin = (q.get("asin") or [""])[0].upper()
        if asin not in meta["asins"]:
            raise ValueError("ASIN này không nằm trong bộ keyword")
        period = (q.get("period") or [KY_CHINH])[0]
        if period not in (KY_CHINH, KY_HIEN_TAI):
            raise ValueError("Kỳ không hợp lệ")
        ten = (q.get("filename") or [""])[0]
        asin_file = cerebro.ASIN_RE.search(ten.upper())
        rows = cerebro.doc_file(self._body(), ten)
        canh_bao = cerebro.kiem_bo_loc(rows, SV_MIN, RANK_MIN, RANK_MAX) if period == KY_CHINH else []
        if asin_file and asin_file.group(0) != asin:
            canh_bao.insert(0, f"Tên file có ASIN {asin_file.group(0)}, khác ASIN đang chọn {asin}")
        # nguon=h10: dữ liệu do extension lấy (vd chuyển bộ từ tool ở máy lên cloud), mặc định là file tải tay
        nguon = (q.get("nguon") or ["file"])[0]
        if nguon not in ("file", "h10"):
            raise ValueError("Nguồn không hợp lệ")
        store.cancel(slug, asin)
        store.save_asin_data(slug, asin, rows=rows, period_used=period, nguon=nguon, canh_bao=canh_bao)
        self._json({"ok": True, "so_kw": len(rows), "canh_bao": canh_bao, "list": tom_tat_bo(meta)})

    def _export(self, slug: str):
        meta = bo_theo(slug)
        if not meta:
            return self._err(404, "Chưa có bộ keyword này")
        t = tom_tat_bo(meta, kem_dong=True)
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["Keyword Phrase", "Search Volume", "Search Volume Trend", "Organic Rank",
                    "ASIN nguon", "So ASIN co", "Ky du lieu"])
        for r in t["rows"]:
            w.writerow([r["keyword"], r["sv"], r["trend"], r["rank"], r["asin"], r["so_asin"],
                        "12/2025" if r["ky"] == KY_CHINH else "hien tai"])
        body = ("﻿" + buf.getvalue()).encode("utf-8")
        self._send(200, body, "text/csv; charset=utf-8",
                   {"Content-Disposition": f"attachment; filename*=UTF-8''{quote(slug)}.csv"})

    def _final(self, slug: str, dang: str, q: dict):
        """Bộ keyword final đã chia biến thể: .xlsx (mỗi loại một sheet) hoặc .md (cho agent đọc).
        Nhận cả tên bộ lẫn Mã sản phẩm (/api/lists/BSV051/final.md) để agent khỏi phải tra tên bộ."""
        meta = bo_theo(slug)
        if not meta:
            return self._err(404, "Chưa có bộ keyword này")
        L, BT = tom_tat_bo(meta, kem_dong=True), tinh_bien_the(meta)
        if dang == "xlsx":
            return self._send(200, xuat.xlsx_bytes(L, BT),
                              "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                              {"Content-Disposition": f"attachment; filename*=UTF-8''{quote(meta['slug'])}-final.xlsx"})
        loai = {x.strip().lower() for x in (q.get("loai") or [""])[0].split(",") if x.strip()}
        md = xuat.markdown(L, BT, kw=q.get("kw") != ["0"], loai=loai or None, bo_phu=q.get("phu") == ["0"])
        self._send(200, md.encode("utf-8"), "text/markdown; charset=utf-8")

    def _bien_the(self, slug: str):
        meta = bo_theo(slug)
        if not meta:
            return self._err(404, "Chưa có bộ keyword này")
        self._json(tinh_bien_the(meta))

    def _dat_nhan(self, slug: str):
        # Nhãn so với sản phẩm cho một biến thể (Sát / Xa / Không hợp; rỗng = bỏ nhãn), lưu riêng cho bộ này
        meta = bo_theo(slug)
        if not meta:
            return self._err(404, "Chưa có bộ keyword này")
        slug = meta["slug"]
        b = self._jbody()
        ten, nhan = str(b.get("ten") or "").strip(), str(b.get("nhan") or "").strip()
        if not ten or (nhan and nhan not in NHAN):
            raise ValueError("Thiếu tên biến thể hoặc nhãn không hợp lệ")
        f = store.list_dir(slug) / "danh_gia.json"
        dg = store._read(f, {})
        dg[ten] = nhan   # rỗng vẫn ghi để đè nhãn cấu hình
        store._write(f, dg)
        self._json(tinh_bien_the(meta))

    def _xoa_kw(self, slug: str):
        # Bỏ keyword khỏi bộ ({keywords}), hoặc khôi phục ({keywords, khoi_phuc: true}; khoi_phuc "het" = tất cả)
        meta = bo_theo(slug)
        if not meta:
            return self._err(404, "Chưa có bộ keyword này")
        slug = meta["slug"]
        b = self._jbody()
        kws = [str(k).strip() for k in b.get("keywords") or [] if str(k).strip()]
        cu = da_xoa(slug)
        if b.get("khoi_phuc") == "het":
            moi = []
        elif b.get("khoi_phuc"):
            bo = {k.lower() for k in kws}
            moi = [k for k in cu if k.lower() not in bo]
        else:
            if not kws:
                raise ValueError("Chưa chọn keyword nào")
            co = {k.lower() for k in cu}
            moi = cu + [k for k in dict.fromkeys(kws) if k.lower() not in co]
        store._write(store.list_dir(slug) / "da_xoa.json", moi)
        self._json({"ok": True, "da_xoa": moi, "doi": abs(len(moi) - len(cu))})

    def _lark_link(self, slug: str):
        meta = store.get_list(slug)
        if not meta:
            return self._err(404, "Chưa có bộ keyword này")
        url = link_bo(slug)
        lark.write_link(meta["record_id"], url)
        self._json({"ok": True, "link": url})

    def _hang_doi(self):
        """Hàng đợi theo bộ: ASIN nào đang chờ / đang lấy, máy nào lấy, bỏ bộ thì bớt bao nhiêu lượt."""
        jobs = store._jobs()
        cho = [j for j in jobs if j["status"] in ("queued", "running")]
        theo_asin: dict[str, set] = {}
        for j in cho:
            theo_asin.setdefault(j["asin"], set()).add(j["slug"])
        dang = {j["asin"] for j in cho if j["status"] == "running"}
        meta = {m["slug"]: m for m in store.lists_by_ma().values()}
        bo: dict[str, dict] = {}
        for j in sorted(cho, key=lambda x: (x["status"] != "running", thu_tu_chay(x))):
            b = bo.get(j["slug"])
            if not b:
                m = meta.get(j["slug"]) or store.get_list(j["slug"]) or {}
                b = bo[j["slug"]] = {"slug": j["slug"], "ma": m.get("ma", ""), "ten": m.get("ten", j["slug"]),
                                     "niche": m.get("niche", ""), "xep_luc": j["created_at"],
                                     "uu_tien": bool(j.get("uu_tien")), "asins": [], "luot_rieng": 0}
            b["asins"].append({"asin": j["asin"], "dang_lay": j["status"] == "running", "uu_tien": bool(j.get("uu_tien")),
                               "ten_may": j.get("ten_may") or "", "ky": j["period"],
                               "bo_khac": len(theo_asin[j["asin"]]) - 1})
            # Lượt chỉ bộ này cần: bỏ bộ là bớt lượt đó (ASIN dùng chung thì bộ khác vẫn chờ)
            if j["status"] == "queued" and len(theo_asin[j["asin"]]) == 1 and j["asin"] not in dang:
                b["luot_rieng"] += 1
        # Thời gian một lượt: trung vị các job xong trong 6 giờ qua
        gan = sorted(j["finished_at"] - j["started_at"] for j in jobs
                     if j.get("started_at") and j.get("finished_at") and j["status"] in ("done", "empty", "failed")
                     and not j.get("dung_lai_tu") and j["finished_at"] > time.time() - 6 * 3600)
        self._json({"ok": True, "bo": list(bo.values()), "so_luot": len(theo_asin),
                    "luot_uu_tien": len({j["asin"] for j in cho if j.get("uu_tien") and j["status"] == "queued"}),
                    "phut_moi_luot": round(gan[len(gan) // 2] / 60, 1) if gan else None,
                    "may": danh_sach_may(), "tam_dung": store.tam_dung()})

    def _uu_tien(self):
        """Ưu tiên danh sách mã: làm xong từng mã một; mã có ASIN dùng chung với nhiều mã trong danh sách
        làm trước, trong mã thì ASIN dùng chung nhiều chạy trước. Body {ma: [...]} hoặc {bo: true} để bỏ ưu tiên."""
        b = self._jbody()
        if b.get("bo"):
            return self._json({"ok": True, "da_bo": store.bo_uu_tien()})
        ds = list(dict.fromkeys(str(x).strip().upper() for x in (b.get("ma") or []) if str(x).strip()))
        if not ds:
            raise ValueError("Chưa nhập mã nào")
        ma_cua = store.ma_cua_slug()
        cho: dict[str, set] = {}          # mã → ASIN đang chờ
        dang = set()
        for j in store._jobs():
            ma = (ma_cua.get(j["slug"]) or "").upper()
            if j["status"] == "running":
                dang.add(j["asin"])
            if ma in ds and j["status"] == "queued":
                cho.setdefault(ma, set()).add(j["asin"])
        thu_tu, xong = sap_uu_tien(ds, cho, dang)
        so_job = store.dat_uu_tien(thu_tu)
        self._json({"ok": True, "so_ma": len(xong), "so_asin": len(thu_tu), "so_job": so_job,
                    "thu_tu_ma": xong, "khong_trong_hang": [m for m in ds if m not in cho]})

    def _bo_hang_doi(self):
        slugs = [str(x) for x in (self._jbody().get("slugs") or [])][:5000]
        if not slugs:
            raise ValueError("Chưa chọn bộ nào")
        self._json({"ok": True, "da_bo": store.bo_khoi_hang(slugs)})

    def _extension_zip(self):
        """Gói extension để cài lên máy khác (Load unpacked)."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for f in sorted((GOC / "extension").iterdir()):
                if f.is_file() and not f.name.startswith("."):
                    z.write(f, "kw-bien-the-extension/" + f.name)
        self._send(200, buf.getvalue(), "application/zip",
                   {"Content-Disposition": 'attachment; filename="kw-bien-the-extension.zip"'})

    def _dung_tool(self):
        dung = bool(self._jbody().get("dung"))
        store.dat_tam_dung(dung)
        self._json({"ok": True, "tam_dung": dung})

    # ------------------------------------------------------------ extension
    def _may(self) -> tuple[str, str]:
        """(id, tên) máy đang gọi. Extension cũ (≤ 0.1.7) không gửi id: gom chung một máy."""
        mid = re.sub(r"[^A-Za-z0-9-]", "", self.headers.get("X-Agent-Id", ""))[:40] or "may-cu"
        return mid, unquote(self.headers.get("X-Agent-Ten", "")).strip()[:60]

    def _agent_seen(self, nhan_job: bool):
        mid, ten = self._may()
        store.agents[mid] = {
            "id": mid, "ten": ten, "last_seen": time.time(),
            "phien_ban": self.headers.get("X-Agent-Version", ""),
            "h10": self.headers.get("X-Agent-H10", "unknown"),
            "san_sang": self.headers.get("X-Agent-Ready", "") == "1",
            "nhan_job": nhan_job,
            "loi": unquote(self.headers.get("X-Agent-Loi", ""))[:300] or None,   # lỗi mới nhất extension đang báo
        }

    def _agent_ping(self):
        # Extension báo còn sống và hỏi hàng đợi; không nhận job, không tính lượt
        if not self._agent_ok():
            return self._err(401, "Sai AGENT_TOKEN")
        self._agent_seen(nhan_job=self.headers.get("X-Agent-Running", "") == "1")
        # Đang dừng tool thì báo hàng trống: extension đóng tab H10 và đứng chờ
        dung = store.tam_dung()
        self._json({"ok": True, "cho": 0 if dung else sum(1 for j in store._jobs() if j["status"] == "queued"),
                    "het_luot": het_luot_ngay(), "tam_dung": dung})

    def _agent_capture(self):
        # Request Cerebro do extension ghi lại (chế độ dò API), lưu nguyên để đọc sau
        if not self._agent_ok():
            return self._err(401, "Sai AGENT_TOKEN")
        items = self._jbody().get("items") or []
        thu_muc = DATA / "capture"
        thu_muc.mkdir(parents=True, exist_ok=True)
        with open(thu_muc / (time.strftime("%Y-%m-%d") + ".jsonl"), "a", encoding="utf-8") as f:
            for it in items[:200]:
                f.write(json.dumps(it, ensure_ascii=False) + "\n")
        self._json({"ok": True, "so": len(items[:200])})

    def _agent_capture_file(self, ten: str):
        # Request H10 đã ghi: chỉ trao cho ai có AGENT_TOKEN (dù đã ẩn cookie/token, vẫn là dữ liệu tài khoản)
        if not self._agent_ok():
            return self._err(401, "Sai AGENT_TOKEN")
        return self._file(DATA / "capture" / ten)

    def _agent_next(self):
        if not self._agent_ok():
            return self._err(401, "Sai AGENT_TOKEN")
        self._agent_seen(nhan_job=True)
        if het_luot_ngay():
            return self._json({"ok": True, "job": None, "ly_do": "het_luot_ngay"})
        if store.tam_dung():
            return self._json({"ok": True, "job": None, "ly_do": "tam_dung"})
        j = store.next_job(may=self._may()[0], ten_may=self._may()[1])
        if not j:
            return self._json({"ok": True, "job": None})
        store.add_usage()
        self._json({"ok": True, "job": {
            "id": j["id"], "asin": j["asin"], "attempt": j["attempt"],
            "filters": {**BO_LOC, "period": j["period"]},
        }})

    def _agent_report(self, job_id: str, kind: str):
        if not self._agent_ok():
            return self._err(401, "Sai AGENT_TOKEN")
        self._agent_seen(nhan_job=True)
        b = self._jbody()
        jobs = {j["id"]: j for j in store._jobs()}
        j = jobs.get(job_id)
        if not j:
            return self._err(404, "Không có job này")
        if kind == "release":
            # H10 đăng xuất giữa chừng: trả job về hàng đợi, hoàn lượt, chạy lại khi đăng nhập
            store.update_job(job_id, status="queued", started_at=None, error=str(b.get("error") or "")[:300])
            store.add_usage(-1)
            return self._json({"ok": True})
        if kind == "fail":
            store.update_job(job_id, status="failed", error=str(b.get("error") or "Không rõ lỗi")[:500],
                             finished_at=time.time())
            return self._json({"ok": True})
        rows = cerebro.chuan_hoa(b.get("rows") or [])
        period_used = b.get("period_used") or j["period"]
        if not rows and j["period"] == KY_CHINH:
            # Kỳ 12/2025 không có kết quả → bỏ bộ lọc kỳ, lấy kỳ hiện tại
            store.update_job(job_id, status="empty", rows=0, finished_at=time.time())
            store.doi_ky_cho(j["asin"], job_id, KY_HIEN_TAI)
            store.enqueue(j["slug"], j["asin"], period=KY_HIEN_TAI, attempt=j["attempt"] + 1, uu_tien=j.get("uu_tien"))
            return self._json({"ok": True, "tiep": "thu_ky_hien_tai"})
        # Kỳ hiện tại là sản phẩm mới: cố ý không lọc SV/rank, nên không cảnh báo về bộ lọc
        canh_bao = cerebro.kiem_bo_loc(rows, SV_MIN, RANK_MIN, RANK_MAX) if rows and period_used == KY_CHINH else []
        luc = time.time()
        store.save_asin_data(j["slug"], j["asin"], rows=rows, period_used=period_used,
                             nguon="h10", canh_bao=canh_bao, fetched_at=luc)
        store.update_job(job_id, status="done" if rows else "empty", rows=len(rows), finished_at=luc)
        chung = store.chia_ket_qua(j["asin"], job_id, rows, period_used, j["slug"], canh_bao, luc)
        chung += store.dien_bo_thieu(j["asin"], rows, period_used, j["slug"], canh_bao, luc)
        self._json({"ok": True, "so_kw": len(rows), "dien_chung": len(chung)})


def main():
    auth.init(HOST)
    if HOST not in auth.LOOPBACK and not AGENT_TOKEN:
        print("  agent   : CHƯA đặt AGENT_TOKEN → extension không gọi được /api/agent/* từ ngoài")
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"KW Biến Thể chạy ở http://{HOST}:{PORT}  ·  link bộ keyword: {PUBLIC_URL}/kw-list/<tên bộ>\n"
          f"  auth    : {'bro-auth ' + auth.BASE_URL if auth.enabled() else 'TẮT' + (' (chỉ chạy ở máy)' if HOST in auth.LOOPBACK else ', không cần đăng nhập')}\n"
          f"  lark    : {lark.BACKEND}  ·  dữ liệu: {DATA}", flush=True)
    lt = luu_tru()
    if os.environ.get("RAILWAY_ENVIRONMENT") and not lt["tren_volume"]:
        print(f"  CẢNH BÁO: {DATA} không nằm trên volume (volume: {lt['volume']}) → deploy lại là mất dữ liệu",
              flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
