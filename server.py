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
  DAILY_LIMIT       số lượt Cerebro tối đa mỗi ngày (mặc định 60)
  SV_MIN / RANK_MIN bộ lọc chuẩn (mặc định 50 / 1)
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
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

import auth
import cerebro
import engine
import lark
from store import KY_CHINH, KY_HIEN_TAI, Store

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
DAILY_LIMIT = int(os.environ.get("DAILY_LIMIT", "60"))
SV_MIN = int(os.environ.get("SV_MIN", "50"))
RANK_MIN = int(os.environ.get("RANK_MIN", "1"))
MAX_UPLOAD = 30 * 1024 * 1024

store = Store(DATA)


def tom_tat_capture() -> list[dict]:
    """Các ngày có request do chế độ "Ghi lại" gửi về: tên file, số dòng, dung lượng."""
    out = []
    for f in sorted((DATA / "capture").glob("*.jsonl")):
        with open(f, "rb") as fh:
            out.append({"file": f.name, "so": sum(1 for _ in fh), "kb": round(f.stat().st_size / 1024)})
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
    "mot_asin_mot_lan": True,
}


def link_bo(slug: str) -> str:
    return f"{PUBLIC_URL}/kw-list/{quote(slug)}"


def trang_thai_asin(slug: str, asins: list[str]) -> list[dict]:
    jobs = store.jobs_for(slug)
    out = []
    for a in asins:
        js = sorted((j for j in jobs if j["asin"] == a), key=lambda j: j["created_at"])
        last = js[-1] if js else None
        d = store.asin_data(slug, a)
        st = {"asin": a, "so_kw": len(d["rows"]) if d else 0,
              "period_used": d["period_used"] if d else None,
              "nguon": d["nguon"] if d else None,
              "canh_bao": d.get("canh_bao", []) if d else [],
              "fetched_at": d["fetched_at"] if d else None, "loi": ""}
        if last and last["status"] in ("queued", "running"):
            st["trang_thai"] = "cho" if last["status"] == "queued" else "dang_lay"
            st["period_dang_thu"] = last["period"]
        elif d is not None:
            st["trang_thai"] = "xong" if d["rows"] else "rong"
        elif last and last["status"] == "failed":
            st["trang_thai"], st["loi"] = "loi", last["error"]
        else:
            st["trang_thai"] = "chua_lay"
        out.append(st)
    return out


def tom_tat_bo(meta: dict, kem_dong: bool = False) -> dict:
    asins = trang_thai_asin(meta["slug"], meta.get("asins") or [])
    out = {**meta, "link": link_bo(meta["slug"]), "trang_thai_asin": asins,
           "so_xong": sum(1 for a in asins if a["trang_thai"] in ("xong", "rong"))}
    if kem_dong:
        data = store.all_asin_data(meta["slug"], meta.get("asins") or [])
        rows, stats = cerebro.gop(data)
        ky = {d["period_used"] for d in data.values() if d["rows"]}
        out.update(rows=rows, stats=stats, ky_tron=len(ky) > 1)
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
    """Chia biến thể 3 tầng (engine.chia_nhom) cho một bộ keyword, nhãn người dùng sửa đè lên nhãn cấu hình."""
    slug = meta["slug"]
    data = {a: d for a, d in store.all_asin_data(slug, meta.get("asins") or []).items() if d.get("rows")}
    rows, stats = cerebro.gop(data)
    ch = cau_hinh(meta["ma"])
    dg = {**ch["danh_gia"], **store._read(store.list_dir(slug) / "danh_gia.json", {})}
    asins = [a for a in meta.get("asins") or [] if a in data]
    if not asins:
        return {"ok": True, "trong": True, "asins": [], "nhan_chon": NHAN}
    res = engine.chia_nhom(rows, asins, ch["neg"], theo_asin=data, target_year=ch["target_year"])
    out = engine.ket_qua_json(res, dg, {"Không hợp"})
    out.update(ok=True, stats=stats, nhan_chon=NHAN, cau_hinh_rieng=ch["rieng"], target_year=ch["target_year"],
               ky={a: data[a].get("period_used") for a in asins})
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
                    meta = store.get_list(m.group(1))
                    if not meta:
                        return self._err(404, "Chưa có bộ keyword này")
                    return self._json({"ok": True, "list": tom_tat_bo(meta, kem_dong=q.get("rows") != ["0"])})
                m = re.fullmatch(r"/api/lists/([^/]+)/export\.csv", path)
                if m:
                    return self._export(m.group(1))
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
                if path == "/api/agent/capture":
                    return self._agent_capture()
                m = re.fullmatch(r"/api/agent/jobs/([a-f0-9]+)/(result|fail)", path)
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
        seen = store.agent_seen
        self._json({
            "ok": True, "bo_loc": BO_LOC, "public_url": PUBLIC_URL,
            "agent": {"online": time.time() - seen < 90, "last_seen": seen or None, **store.agent_info},
            "luot_hom_nay": store.usage_today(), "gioi_han_ngay": DAILY_LIMIT,
            "hang_doi": store.queue_size(), "luu_tru": luu_tru(), "capture": tom_tat_capture(),
        })

    def _products(self, refresh: bool):
        items = lark.list_products(refresh)
        out = []
        for p in items:
            meta = store.list_by_ma(p["ma"])
            out.append({**p, "bo": tom_tat_bo(meta) if meta else None,
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
        con_lai = DAILY_LIMIT - store.usage_today() - store.queue_size()
        if len(can) > max(con_lai, 0):
            raise ValueError(f"Vượt giới hạn {DAILY_LIMIT} lượt Cerebro/ngày (còn {max(con_lai, 0)} lượt)")
        for a in can:
            store.enqueue(slug, a)
        self._json({"ok": True, "xep_hang": can, "list": tom_tat_bo(meta)})

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
        canh_bao = cerebro.kiem_bo_loc(rows, SV_MIN, RANK_MIN) if period == KY_CHINH else []
        if asin_file and asin_file.group(0) != asin:
            canh_bao.insert(0, f"Tên file có ASIN {asin_file.group(0)}, khác ASIN đang chọn {asin}")
        store.cancel(slug, asin)
        store.save_asin_data(slug, asin, rows=rows, period_used=period, nguon="file", canh_bao=canh_bao)
        self._json({"ok": True, "so_kw": len(rows), "canh_bao": canh_bao, "list": tom_tat_bo(meta)})

    def _export(self, slug: str):
        meta = store.get_list(slug)
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

    def _bien_the(self, slug: str):
        meta = store.get_list(slug)
        if not meta:
            return self._err(404, "Chưa có bộ keyword này")
        self._json(tinh_bien_the(meta))

    def _dat_nhan(self, slug: str):
        # Nhãn so với sản phẩm cho một biến thể (Sát / Xa / Không hợp; rỗng = bỏ nhãn), lưu riêng cho bộ này
        meta = store.get_list(slug)
        if not meta:
            return self._err(404, "Chưa có bộ keyword này")
        b = self._jbody()
        ten, nhan = str(b.get("ten") or "").strip(), str(b.get("nhan") or "").strip()
        if not ten or (nhan and nhan not in NHAN):
            raise ValueError("Thiếu tên biến thể hoặc nhãn không hợp lệ")
        f = store.list_dir(slug) / "danh_gia.json"
        dg = store._read(f, {})
        dg[ten] = nhan   # rỗng vẫn ghi để đè nhãn cấu hình
        store._write(f, dg)
        self._json(tinh_bien_the(meta))

    def _lark_link(self, slug: str):
        meta = store.get_list(slug)
        if not meta:
            return self._err(404, "Chưa có bộ keyword này")
        url = link_bo(slug)
        lark.write_link(meta["record_id"], url)
        self._json({"ok": True, "link": url})

    # ------------------------------------------------------------ extension
    def _agent_seen(self, nhan_job: bool):
        store.agent_seen = time.time()
        store.agent_info = {
            "phien_ban": self.headers.get("X-Agent-Version", ""),
            "h10": self.headers.get("X-Agent-H10", "unknown"),
            "san_sang": self.headers.get("X-Agent-Ready", "") == "1",
            "nhan_job": nhan_job,
        }

    def _agent_ping(self):
        # Extension báo còn sống và hỏi hàng đợi; không nhận job, không tính lượt
        if not self._agent_ok():
            return self._err(401, "Sai AGENT_TOKEN")
        self._agent_seen(nhan_job=self.headers.get("X-Agent-Running", "") == "1")
        self._json({"ok": True, "cho": sum(1 for j in store._jobs() if j["status"] == "queued"),
                    "het_luot": store.usage_today() >= DAILY_LIMIT})

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
        if store.usage_today() >= DAILY_LIMIT:
            return self._json({"ok": True, "job": None, "ly_do": "het_luot_ngay"})
        j = store.next_job()
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
        if kind == "fail":
            store.update_job(job_id, status="failed", error=str(b.get("error") or "Không rõ lỗi")[:500],
                             finished_at=time.time())
            return self._json({"ok": True})
        rows = cerebro.chuan_hoa(b.get("rows") or [])
        period_used = b.get("period_used") or j["period"]
        if not rows and j["period"] == KY_CHINH:
            # Kỳ 12/2025 không có kết quả → bỏ bộ lọc kỳ, lấy kỳ hiện tại
            store.update_job(job_id, status="empty", rows=0, finished_at=time.time())
            store.enqueue(j["slug"], j["asin"], period=KY_HIEN_TAI, attempt=j["attempt"] + 1)
            return self._json({"ok": True, "tiep": "thu_ky_hien_tai"})
        # Kỳ hiện tại là sản phẩm mới: cố ý không lọc SV/rank, nên không cảnh báo về bộ lọc
        canh_bao = cerebro.kiem_bo_loc(rows, SV_MIN, RANK_MIN) if rows and period_used == KY_CHINH else []
        store.save_asin_data(j["slug"], j["asin"], rows=rows, period_used=period_used,
                             nguon="h10", canh_bao=canh_bao)
        store.update_job(job_id, status="done" if rows else "empty", rows=len(rows),
                         finished_at=time.time())
        self._json({"ok": True, "so_kw": len(rows)})


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
