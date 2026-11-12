"""
Lưu trữ bằng file JSON trong DATA_DIR (đủ cho bản tạm; khi ghép app khác thay bằng DB).

  data/lists/<slug>/meta.json     thông tin bộ keyword (mã, tên, ASIN, bộ lọc)
  data/lists/<slug>/<ASIN>.json   dòng keyword của từng ASIN + kỳ đã dùng + nguồn
                                  (cùng ASIN ở bộ khác thì chép từ bộ đã lấy, ghi dung_lai_tu)
  data/jobs.json                  hàng đợi job lấy Cerebro cho extension
  data/analysis/<mã>.json         ghi chú phân tích ảnh sản phẩm
  data/usage.json                 số lượt Cerebro đã dùng theo ngày
"""

from __future__ import annotations

import json
import re
import threading
import time
import unicodedata
import uuid
from datetime import datetime
from pathlib import Path

KY_CHINH = "2025-12"      # kỳ Cerebro chuẩn: tháng 12/2025
KY_HIEN_TAI = "current"   # dự phòng khi kỳ chuẩn không có dữ liệu

khoa = threading.RLock()


def thu_tu_chay(j: dict) -> tuple:
    """Khoá sắp hàng đợi: job ưu tiên trước (lần ưu tiên mới nhất trước, rồi theo thứ tự đã xếp),
    còn lại theo giờ xếp."""
    u = j.get("uu_tien")
    return (0, -u[0], u[1], j["created_at"]) if u else (1, 0, 0, j["created_at"])


class Store:
    def __init__(self, root: Path):
        self.root = root
        (root / "lists").mkdir(parents=True, exist_ok=True)
        (root / "analysis").mkdir(parents=True, exist_ok=True)
        self.agents: dict[str, dict] = {}   # máy chạy extension: id → thông tin lần báo gần nhất
        # Tóm tắt file ASIN (số kw, kỳ, nguồn…) theo mtime. Lưu xuống ổ để khởi động lại (mỗi lần deploy) không phải
        # đọc lại ~5.000 file ASIN chỉ để đếm keyword — việc đó từng làm danh sách mã treo vài phút.
        self._tt_file = root / "tom_tat_asin.json"
        self._tt_cache: dict[Path, tuple[float, dict | None]] = {
            root / k: (v[0], v[1]) for k, v in self._read(self._tt_file, {}).items()}
        self._tt_moi = False
        self._tt_luu_luc = 0.0

    # ------------------------------------------------------------ tiện ích file
    def _read(self, p: Path, default):
        try:
            return json.loads(p.read_text("utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return default

    def _write(self, p: Path, obj) -> None:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), "utf-8")
        tmp.replace(p)

    # ------------------------------------------------------------ tên bộ keyword
    @staticmethod
    def slugify(s: str) -> str:
        s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
        return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")

    @classmethod
    def ten_bo(cls, ma: str, niche: str, product: str) -> tuple[str, str]:
        """Tên bộ = {Mã nội bộ}-{niche + product}. Trả (tên hiển thị, slug cho URL)."""
        niche, product = (niche or "").strip(), (product or "").strip()
        ten = niche
        if product and not cls.slugify(niche).endswith(cls.slugify(product)):
            ten = f"{niche} {product}".strip()
        ma_s = re.sub(r"[^A-Za-z0-9]+", "", ma or "")
        return f"{ma} - {ten}", f"{ma_s}-{cls.slugify(ten)}".strip("-")

    # ------------------------------------------------------------ bộ keyword
    def list_dir(self, slug: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*", slug or ""):
            raise ValueError("Tên bộ keyword không hợp lệ")
        return self.root / "lists" / slug

    def get_list(self, slug: str) -> dict | None:
        return self._read(self.list_dir(slug) / "meta.json", None)

    def list_by_ma(self, ma: str) -> dict | None:
        with khoa:
            best = None
            for f in (self.root / "lists").glob("*/meta.json"):
                m = self._read(f, None)
                if m and m.get("ma") == ma and (best is None or m["updated_at"] > best["updated_at"]):
                    best = m
            return best

    def lists_by_ma(self) -> dict[str, dict]:
        """Bộ mới nhất của từng mã, đọc tất cả meta một lượt (danh sách mã gọi cho ~1.500 mã)."""
        best: dict[str, dict] = {}
        for f in (self.root / "lists").glob("*/meta.json"):
            m = self._read(f, None)
            if m and m.get("ma") and (m["ma"] not in best or m["updated_at"] > best[m["ma"]]["updated_at"]):
                best[m["ma"]] = m
        return best

    def ma_cua_slug(self) -> dict[str, str]:
        """slug → mã nội bộ, cho mọi bộ (kể cả bộ cũ của mã trùng)."""
        out = {}
        for f in (self.root / "lists").glob("*/meta.json"):
            m = self._read(f, None)
            if m and m.get("ma"):
                out[f.parent.name] = m["ma"]
        return out

    def save_list(self, meta: dict) -> dict:
        with khoa:
            meta["updated_at"] = time.time()
            self._write(self.list_dir(meta["slug"]) / "meta.json", meta)
            return meta

    def upsert_list(self, *, ma, record_id, niche, product, asins, nguoi="") -> dict:
        ten, slug = self.ten_bo(ma, niche, product)
        if not slug or slug == ma:
            raise ValueError("Cần nhập niche hoặc product để đặt tên bộ keyword")
        with khoa:
            meta = self.get_list(slug) or {
                "slug": slug, "ma": ma, "created_at": time.time(), "created_by": nguoi,
            }
            meta.update(ten=ten, record_id=record_id, niche=niche, product=product, asins=asins)
            return self.save_list(meta)

    def asin_data(self, slug: str, asin: str) -> dict | None:
        return self._read(self.list_dir(slug) / f"{asin}.json", None)

    def save_asin_data(self, slug: str, asin: str, *, rows, period_used, nguon, canh_bao=None,
                       fetched_at=None, dung_lai_tu=None):
        with khoa:
            d = {"asin": asin, "rows": rows, "period_used": period_used, "nguon": nguon,
                 "canh_bao": canh_bao or [], "fetched_at": fetched_at or time.time()}
            if dung_lai_tu:
                d.update(dung_lai_tu=dung_lai_tu, dung_lai_luc=time.time())
            self._write(self.list_dir(slug) / f"{asin}.json", d)

    def tim_du_lieu_asin(self, asin: str, tru_slug: str = "") -> tuple[str, dict] | None:
        """Dữ liệu Cerebro (extension lấy) mới nhất của ASIN ở bộ khác → (slug, dữ liệu).
        Một ASIN chỉ cần chạy Cerebro một lần rồi dùng chung cho mọi bộ có nó; file tải tay không tính
        vì không chắc đúng bộ lọc."""
        best = None
        for f in (self.root / "lists").glob(f"*/{asin}.json"):
            if f.parent.name == tru_slug:
                continue
            d = self._read(f, None)
            if d and d.get("nguon") == "h10" and (best is None or d["fetched_at"] > best[1]["fetched_at"]):
                best = (d.get("dung_lai_tu") or f.parent.name, d)
        return best

    def dung_lai_asin(self, slug: str, asin: str) -> bool:
        """Chép dữ liệu ASIN đã có ở bộ khác vào bộ này. Trả True nếu chép được."""
        tim = self.tim_du_lieu_asin(asin, slug)
        if not tim:
            return False
        nguon_slug, d = tim
        self.save_asin_data(slug, asin, rows=d["rows"], period_used=d["period_used"], nguon="h10",
                            canh_bao=d.get("canh_bao"), fetched_at=d["fetched_at"], dung_lai_tu=nguon_slug)
        return True

    def asin_tom_tat(self, slug: str, asin: str) -> dict | None:
        """Như asin_data nhưng không kèm dòng keyword (chỉ số kw), nhớ theo mtime để khỏi đọc lại file lớn."""
        p = self.list_dir(slug) / f"{asin}.json"
        try:
            mt = p.stat().st_mtime
        except FileNotFoundError:
            return None
        c = self._tt_cache.get(p)
        if c and c[0] == mt:
            return c[1]
        d = self._read(p, None)
        if d is not None:
            d = {**{k: v for k, v in d.items() if k != "rows"}, "so_kw": len(d.get("rows") or [])}
        self._tt_cache[p] = (mt, d)
        self._tt_moi = True
        return d

    def luu_tom_tat(self, toi_thieu_giay: float = 60) -> None:
        """Ghi bộ nhớ tóm tắt ASIN xuống ổ khi có mục mới (tối đa mỗi phút một lần)."""
        if not self._tt_moi or time.time() - self._tt_luu_luc < toi_thieu_giay:
            return
        self._tt_moi, self._tt_luu_luc = False, time.time()
        try:
            self._write(self._tt_file, {str(p.relative_to(self.root)): [mt, d] for p, (mt, d) in list(self._tt_cache.items())})
        except (OSError, ValueError):
            self._tt_moi = True

    def all_asin_data(self, slug: str, asins: list[str]) -> dict[str, dict]:
        out = {}
        for a in asins:
            d = self.asin_data(slug, a)
            if d is not None:
                out[a] = d
        return out

    # ------------------------------------------------------------ hàng đợi job
    def _jobs(self) -> list[dict]:
        return self._read(self.root / "jobs.json", [])

    def _save_jobs(self, jobs: list[dict]) -> None:
        cutoff = time.time() - 30 * 86400
        jobs = [j for j in jobs if j["created_at"] > cutoff or j["status"] in ("queued", "running")]
        self._write(self.root / "jobs.json", jobs)

    def jobs_for(self, slug: str) -> list[dict]:
        return [j for j in self._jobs() if j["slug"] == slug]

    def enqueue(self, slug: str, asin: str, period: str = KY_CHINH, attempt: int = 1, uu_tien=None) -> dict:
        with khoa:
            jobs = self._jobs()
            for j in jobs:
                if j["slug"] == slug and j["asin"] == asin and j["status"] in ("queued", "running"):
                    return j
            # ASIN đã được ưu tiên ở bộ khác thì job mới cùng ASIN đứng cùng chỗ
            uu_tien = uu_tien or next((x["uu_tien"] for x in jobs if x["asin"] == asin and x.get("uu_tien")
                                       and x["status"] in ("queued", "running")), None)
            j = {"id": uuid.uuid4().hex[:12], "slug": slug, "asin": asin, "period": period,
                 "attempt": attempt, "status": "queued", "created_at": time.time(),
                 "started_at": None, "finished_at": None, "error": "", "rows": None}
            if uu_tien:
                j["uu_tien"] = uu_tien
            jobs.append(j)
            self._save_jobs(jobs)
            return j

    def chia_ket_qua(self, asin: str, tru_job: str, rows, period_used, nguon_slug, canh_bao, fetched_at) -> list[str]:
        """Một job xong thì điền luôn cho các bộ khác đang chờ cùng ASIN (không chạy Cerebro lại)."""
        with khoa:
            jobs, xong = self._jobs(), []
            for j in jobs:
                if j["asin"] == asin and j["id"] != tru_job and j["status"] == "queued":
                    self.save_asin_data(j["slug"], asin, rows=rows, period_used=period_used, nguon="h10",
                                        canh_bao=canh_bao, fetched_at=fetched_at, dung_lai_tu=nguon_slug)
                    j.update(status="done" if rows else "empty", rows=len(rows), finished_at=time.time(),
                             dung_lai_tu=nguon_slug)
                    xong.append(j["slug"])
            if xong:
                self._save_jobs(jobs)
            return xong

    def dien_bo_thieu(self, asin: str, rows, period_used, nguon_slug, canh_bao, fetched_at) -> list[str]:
        """Bộ có ASIN này mà chưa có dữ liệu và không có job chờ (chưa xếp, đã bỏ khỏi hàng đợi, lỗi)
        → chép luôn, để mã trùng ASIN không phải đợi ai bấm lấy keyword."""
        dang = {j["slug"] for j in self._jobs() if j["asin"] == asin and j["status"] in ("queued", "running")}
        xong = []
        for f in (self.root / "lists").glob("*/meta.json"):
            m = self._read(f, None)
            if (not m or asin not in (m.get("asins") or []) or f.parent.name in dang
                    or (f.parent / f"{asin}.json").exists()):
                continue
            self.save_asin_data(f.parent.name, asin, rows=rows, period_used=period_used, nguon="h10",
                                canh_bao=canh_bao, fetched_at=fetched_at, dung_lai_tu=nguon_slug)
            xong.append(f.parent.name)
        return xong

    def dung_lai_tat_ca(self) -> dict:
        """Quét mọi bộ: ASIN chưa có dữ liệu, không có job chờ, mà bộ khác đã lấy → chép sang (0 lượt)."""
        dang = {(j["slug"], j["asin"]) for j in self._jobs() if j["status"] in ("queued", "running")}
        can: dict[str, list[str]] = {}
        for f in (self.root / "lists").glob("*/meta.json"):
            m = self._read(f, None)
            for a in (m or {}).get("asins") or []:
                if (f.parent.name, a) not in dang and not (f.parent / f"{a}.json").exists():
                    can.setdefault(a, []).append(f.parent.name)
        so_o, so_bo = 0, set()
        for a, slugs in can.items():
            tim = self.tim_du_lieu_asin(a)
            if not tim:
                continue
            nguon_slug, d = tim
            for slug in slugs:
                self.save_asin_data(slug, a, rows=d["rows"], period_used=d["period_used"], nguon="h10",
                                    canh_bao=d.get("canh_bao"), fetched_at=d["fetched_at"], dung_lai_tu=nguon_slug)
                so_o += 1
                so_bo.add(slug)
        return {"so_o": so_o, "so_bo": len(so_bo), "so_asin_chua_co": sum(1 for a in can if not self.tim_du_lieu_asin(a))}

    def doi_ky_cho(self, asin: str, tru_job: str, period: str) -> None:
        """Kỳ 12/2025 của ASIN trống: các job khác cùng ASIN đang chờ kỳ đó chuyển sang kỳ mới luôn."""
        with khoa:
            jobs = self._jobs()
            for j in jobs:
                if j["asin"] == asin and j["id"] != tru_job and j["status"] == "queued" and j["period"] != period:
                    j.update(period=period, attempt=j["attempt"] + 1)
            self._save_jobs(jobs)

    def asin_dang_cho(self) -> set[str]:
        return {j["asin"] for j in self._jobs() if j["status"] in ("queued", "running")}

    def dat_uu_tien(self, asins: list[str]) -> int:
        """Đưa các ASIN này lên đầu hàng đợi theo đúng thứ tự cho. Lần ưu tiên sau đứng trước lần trước.
        Trả số job được ưu tiên."""
        lo, vi_tri, so = time.time(), {a: i for i, a in enumerate(asins)}, 0
        with khoa:
            jobs = self._jobs()
            for j in jobs:
                if j["status"] == "queued" and j["asin"] in vi_tri:
                    j["uu_tien"] = [lo, vi_tri[j["asin"]]]
                    so += 1
            if so:
                self._save_jobs(jobs)
        return so

    def bo_uu_tien(self) -> int:
        so = 0
        with khoa:
            jobs = self._jobs()
            for j in jobs:
                if j.pop("uu_tien", None) and j["status"] == "queued":
                    so += 1
            self._save_jobs(jobs)
        return so

    def bo_khoi_hang(self, slugs: list[str]) -> int:
        """Bỏ mọi job đang chờ của các bộ này (job đang lấy dở để chạy cho xong). Trả số job đã bỏ."""
        slugs, so = set(slugs), 0
        with khoa:
            jobs = self._jobs()
            for j in jobs:
                if j["slug"] in slugs and j["status"] == "queued":
                    j.update(status="cancelled", finished_at=time.time())
                    so += 1
            if so:
                self._save_jobs(jobs)
        return so

    def cancel(self, slug: str, asin: str) -> None:
        with khoa:
            jobs = self._jobs()
            for j in jobs:
                if j["slug"] == slug and j["asin"] == asin and j["status"] == "queued":
                    j.update(status="cancelled", finished_at=time.time())
            self._save_jobs(jobs)

    def next_job(self, stale_sec: int = 600, may: str = "", ten_may: str = "") -> dict | None:
        """Job cũ nhất đang chờ. Job 'running' quá stale_sec coi như extension đã rớt → trả lại hàng."""
        with khoa:
            jobs = self._jobs()
            now = time.time()
            for j in jobs:
                if j["status"] == "running" and now - (j["started_at"] or now) > stale_sec:
                    j.update(status="queued", started_at=None, error="Extension không trả kết quả, xếp lại")
            # ASIN đang chạy ở bộ khác thì job cùng ASIN đứng chờ: xong sẽ được điền chung
            dang_chay = {j["asin"] for j in jobs if j["status"] == "running"}
            q = [j for j in jobs if j["status"] == "queued" and j["asin"] not in dang_chay]
            if not q:
                self._save_jobs(jobs)
                return None
            j = min(q, key=thu_tu_chay)
            j.update(status="running", started_at=now, may=may, ten_may=ten_may)
            self._save_jobs(jobs)
            return dict(j)

    def update_job(self, job_id: str, **kw) -> dict | None:
        with khoa:
            jobs = self._jobs()
            for j in jobs:
                if j["id"] == job_id:
                    j.update(kw)
                    self._save_jobs(jobs)
                    return dict(j)
            return None

    def queue_size(self) -> int:
        """Số lượt Cerebro hàng đợi sẽ tốn: mỗi ASIN một lượt, dù nhiều bộ cùng chờ."""
        return len(self.asin_dang_cho())

    # ------------------------------------------------------------ dừng / chạy tool
    def tam_dung(self) -> bool:
        """Người dùng bấm Dừng tool: extension không nhận job mới (hàng đợi giữ nguyên)."""
        return bool(self._read(self.root / "tam_dung.json", {}).get("dung"))

    def dat_tam_dung(self, dung: bool) -> None:
        self._write(self.root / "tam_dung.json", {"dung": dung, "luc": time.time()})

    # ------------------------------------------------------------ lượt dùng / ngày
    def usage_today(self) -> int:
        return self._read(self.root / "usage.json", {}).get(datetime.now().strftime("%Y-%m-%d"), 0)

    def add_usage(self, n: int = 1) -> None:
        with khoa:
            u = self._read(self.root / "usage.json", {})
            d = datetime.now().strftime("%Y-%m-%d")
            u[d] = u.get(d, 0) + n
            self._write(self.root / "usage.json", dict(sorted(u.items())[-60:]))

    # ------------------------------------------------------------ phân tích ảnh
    def get_analysis(self, ma: str) -> dict:
        return self._read(self.root / "analysis" / f"{self.slugify(ma) or 'x'}.json", {})

    def save_analysis(self, ma: str, data: dict) -> dict:
        data = {**data, "ma": ma, "updated_at": time.time()}
        with khoa:
            self._write(self.root / "analysis" / f"{self.slugify(ma) or 'x'}.json", data)
        return data
